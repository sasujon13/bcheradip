"""Opt-in, normal-browser catalogue collection. No API bypass or supplier orders.

Password login remains in process memory. An explicitly selected, dedicated
Chrome profile may retain an owner-created sign-in; never read/export cookies,
copy a personal profile or bypass authentication challenges.
"""
from collections import Counter, deque
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import logging
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlparse, urljoin
from django.db import close_old_connections, transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException
from .models import Supplier, SupplierJob
from .supplier_service import DB, ACTIVE, snapshot_row, audit, finish
from .supplier_api import SnapshotSerializer
from .supplier_connectors import RESTRICTED

SITES = {
    'business_koro': (2, 'https://www.businesskoro.com', '/dashboard/products'),
    'shopbase': (1, 'https://shopbasebd.com', '/store/products/all'),
    'uddoog': (3, 'https://dropshop.com.bd', '/dpanel/products/new'),
    'selfshop': (4, 'https://selfshop.com.bd', '/all-suppliers'),
    'dropbazar': (6, 'https://dropbazarbd.com', '/admin/store/browse'),
    'dropify': (7, 'https://www.dropifybd.com', '/products-list'),
    'resellkori': (8, 'https://resellkori.com', '/products/'),
    'dropshipping': (9, 'https://www.dropshipping.com.bd', '/dropshipper/products/show/all'),
}
MAX_BROWSER_JOBS = 2  # bounded across sources; each source still has a single job


class CollectionStopped(ValueError):
    pass


class CollectionLimitReached(CollectionStopped):
    pass


def amount(value):
    if value is None:
        return None
    value = str(value).translate(str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')).replace(',', '')
    found = re.findall(r'\d+(?:\.\d+)?', value)
    # Do not turn a negative price/range/combined old-and-new-price label
    # into an apparently confirmed positive single-unit buying cost.
    if len(found) != 1 or re.search(r'[-\u2212]\s*[^0-9]*\d', value):
        return None
    try:
        result = Decimal(found[0])
        return str(result.quantize(Decimal('.01'))) if result.is_finite() and 0 <= result < Decimal('1000000000000') else None
    except InvalidOperation:
        return None


def row_for(item, page, category='', vendor='not-provided'):
    from .supplier_media import safe_images
    category = item.get('category') or category
    url = item.get('url') or page
    ident = str(item.get('id') or urlparse(url).path.rstrip('/').split('/')[-1])
    if not ident or len(ident) > 120:
        # Same stable URL key used by the signed-in browser snapshot importer.
        # It is explicitly a derived identity, never a supplier-issued SKU.
        h1, h2 = 2166136261, 5381
        for char in url:
            code = ord(char)
            if code > 0xffff:
                code = 0xd800 + ((code - 0x10000) >> 10)
            h1 = ((h1 ^ code) * 16777619) & 0xffffffff
            h2 = ((h2 * 33) ^ code) & 0xffffffff
        ident = f'url-{h1:x}-{h2:x}'
    return {'external_id': ident, 'variant_id': str(item.get('variant') or '')[:120], 'vendor_id': vendor,
        'warehouse_id': '', 'title': item['title'].strip()[:255], 'url': url,
        'identity': {'authenticity': 'unverified', 'tax_basis': 'unconfirmed', **({'category': category[:160]} if category else {})},
        'source_price': amount(item.get('price')), 'currency': 'BDT',
        'availability': item.get('stock') if item.get('stock') in ('in_stock', 'out_of_stock') else 'unconfirmed',
        'quantity': None, 'weight_grams': None, 'single_unit': False, 'observed_at': timezone.now().isoformat(),
        'preview_images': safe_images(item.get('images') or ([item['image']] if item.get('image') else []))}


def start_job(site, actor=None, *, queued=False):
    _, origin, path = SITES[site]
    host = urlparse(origin).hostname.removeprefix('www.')
    with transaction.atomic(using=DB):
        matches = [s for s in Supplier.objects.using(DB).select_for_update().all()
                   if urlparse(s.website).hostname and urlparse(s.website).hostname.removeprefix('www.') == host]
        if len(matches) != 1:
            raise CollectionStopped('Exactly one configured supplier must match the approved website origin.')
        supplier = matches[0]
        if SupplierJob.objects.using(DB).filter(runner='browser', status__in=ACTIVE).count() >= MAX_BROWSER_JOBS:
            raise CollectionStopped('Two browser collectors are already active. Wait or cancel one before starting another.')
        if not supplier.enabled or not supplier.terms_confirmed:
            raise CollectionStopped('Enable this source with recorded owner-approved collection scope first.')
        if SupplierJob.objects.using(DB).filter(supplier=supplier, status__in=ACTIVE).exists():
            raise CollectionStopped('This supplier already has an active job. Wait or cancel before restarting.')
        job = SupplierJob.objects.using(DB).create(supplier=supplier, runner='browser', action='collect', actor_id=actor,
            status='queued' if queued else 'running', activity='Starting authorised read-only browser collection',
            payload={'site': site, 'checkpoint': origin + path})
        audit('browser_collection_started', actor, supplier, job_id=str(job.pk), scope=origin + path)
        return job


def site_for_supplier(supplier):
    host = urlparse(supplier.website).hostname
    return next((site for site, (_, origin, _) in SITES.items()
                 if host and host.removeprefix('www.') == urlparse(origin).hostname.removeprefix('www.')), None)


def launch_job(supplier, username, password, actor):
    """Fixed child command, ephemeral stdin only; no password in argv/files/DB."""
    site = site_for_supplier(supplier)
    if not site:
        raise CollectionStopped('No approved browser parser is mapped for this website.')
    job = start_job(site, actor, queued=True)
    directory = Path(settings.BASE_DIR) / 'private_suppliers' / 'browser-jobs'
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        log = directory / (str(job.pk) + '.log')
        fd = os.open(log, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            process = subprocess.Popen([sys.executable, str(Path(settings.BASE_DIR) / 'manage.py'),
                'collect_supplier_browser', '--supplier', site, '--job-id', str(job.pk), '--input-json'],
                cwd=settings.BASE_DIR, stdin=subprocess.PIPE, stdout=output, stderr=output,
                text=True, encoding='utf-8', shell=False,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}))
            try:
                process.stdin.write(json.dumps({'username': username, 'password': password}) + '\n')
                process.stdin.close()
            except (BrokenPipeError, OSError):
                process.terminate()
                raise CollectionStopped('Browser process could not accept the one-run login. Credentials were not stored.') from None
    except (OSError, CollectionStopped):
        finish(job, 'failed', 'Browser process could not be started. Credentials were not stored.')
        raise CollectionStopped('Browser process could not be started. Check server runtime and protected log directory.') from None
    return job


class BrowserCollector:
    def __init__(self, site, job, username, password, *, headless=True, max_pages=1000, fill_missing_prices=False, fill_missing_categories=False, start_page=1, use_browser_profile=False, report=print):
        self.site, self.job, self.username, self.password = site, job, username, password
        self.origin, self.start = SITES[site][1:]
        self.allowed_host = urlparse(self.origin).hostname.removeprefix('www.')
        self.headless, self.max_pages, self.report = headless, max_pages, report
        self.driver = None
        self.phase = 'starting browser'
        self.seen, self.pages, self.counts = set(), 0, Counter()
        self.warnings = []
        self.last_db_refresh = 0
        self.fill_missing_prices = fill_missing_prices
        self.start_page = start_page
        self.fill_missing_categories = fill_missing_categories
        self.use_browser_profile = use_browser_profile

    def check(self):
        if time.monotonic() - self.last_db_refresh > 30:
            close_old_connections()
            self.last_db_refresh = time.monotonic()
        job = SupplierJob.objects.using(DB).select_related('supplier').get(pk=self.job.pk)
        if job.status == 'cancel_requested':
            raise CollectionStopped('Cancellation requested; already saved identities are retained.')
        if job.status != 'running' or not job.supplier.enabled or not job.supplier.terms_confirmed:
            raise CollectionStopped('Collection authority changed; stopped without changing shop inventory.')
        if job.actor_id:
            from .supplier_service import actor_authorized
            if not actor_authorized(job):
                raise CollectionStopped('The initiating account no longer has collection permission.')

    def safe_url(self, url):
        raw = urlparse(url)
        if raw.scheme and not raw.hostname:
            raise CollectionStopped('Malformed absolute supplier URL was refused.')
        p = urlparse(urljoin(self.origin, url))
        if p.scheme != 'https' or p.username or p.password or not p.hostname or p.port not in (None,443) or p.hostname.removeprefix('www.') != self.allowed_host:
            raise CollectionStopped('Navigation outside the approved supplier HTTPS origin was refused.')
        return p.geturl()

    def goto(self, url):
        self.check()
        self.driver.get(self.safe_url(url))
        self.safe_url(self.driver.current_url)
        self.challenge()

    def challenge(self):
        text = self.driver.find_element(By.TAG_NAME, 'body').text.casefold()
        if any(s in text for s in ('verify you are human', 'checking your browser', 'access denied', 'complete the captcha', 'enter otp', 'one-time password')):
            raise CollectionStopped('Supplier requires CAPTCHA/OTP or denies access. Manual supplier action is required; no bypass attempted.')
        if self.driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="recaptcha"],iframe[src*="hcaptcha"]'):
            raise CollectionStopped('Supplier CAPTCHA detected. Complete normal sign-in manually; no automated bypass is supported.')
        if any(s in text for s in ('your connection is not private', 'privacy error', 'net::err_cert', 'connection is not secure')):
            raise CollectionStopped('Browser security/certificate warning detected. No warning bypass or TLS override was attempted.')

    def login(self):
        self.phase = 'normal supplier sign-in'
        if self.use_browser_profile:
            # A visible, owner-signed-in profile is local to this machine. A
            # profile alone is never proof of authentication.
            if self.site == 'resellkori':
                self.goto(self.origin + '/account/')
                self.challenge()
                if any(e.is_displayed() for e in self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')):
                    raise CollectionStopped('ResellKori is not signed in in the dedicated Chrome profile. Sign in there and retry.')
                if not self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="logout"],a[href*="customer-logout"]'):
                    raise CollectionStopped('ResellKori account state could not be verified in Chrome; collection stopped.')
                return
            raise CollectionStopped('Signed-in Chrome profile verification has only been mapped for ResellKori.')
        if self.site == 'selfshop':
            self.goto(self.origin)
            # The desktop sign-in trigger is a div, not a button. Use the
            # observed public label; never silently collect as authenticated.
            trigger = WebDriverWait(self.driver, 20).until(lambda d: next((e for e in
                d.find_elements(By.XPATH, "//*[normalize-space()='Hello, Sign in']") if e.is_displayed()), None))
            trigger.click()
        elif self.site == 'resellkori':
            self.goto(self.origin + '/account/')
        elif self.site in ('shopbase', 'dropify'):
            self.goto(self.origin + ('/store/login' if self.site == 'shopbase' else '/dropshipper/login'))
        else:
            self.goto(self.origin + self.start)
        # Normal access may redirect to the actual login form. No guessed API requests.
        try:
            password = WebDriverWait(self.driver, 15).until(lambda d: next((e for e in d.find_elements(By.CSS_SELECTOR, 'input[type="password"]') if e.is_displayed()), None))
        except TimeoutException:
            self.challenge()
            raise CollectionStopped('A normal sign-in form was not exposed. No authenticated connection is claimed.') from None
        self.safe_url(self.driver.current_url)

        self.challenge()
        forms = password.find_elements(By.XPATH, './ancestor::form[1]')
        dialogs = password.find_elements(By.XPATH, './ancestor::*[@role="dialog"][1]')
        scope = forms[0] if forms else dialogs[0] if dialogs else self.driver
        inputs = [e for e in scope.find_elements(By.CSS_SELECTOR, 'input') if e.is_displayed() and e.get_attribute('type') in ('text', 'email', 'tel', 'number')
                  and e.get_attribute('name') not in ('search', 's')
                  and not re.search(r'search|খুঁজুন', e.get_attribute('placeholder') or '', re.I)]
        if not inputs:
            raise CollectionStopped('Normal login form could not be mapped safely; no credentials were submitted.')
        inputs.sort(key=lambda e: 0 if re.search(r'phone|mobile|username|email|login|user', e.get_attribute('name') or '', re.I) else 1)
        self.check()
        inputs[0].clear(); inputs[0].send_keys(self.username)
        password.clear(); password.send_keys(self.password)
        submit = [e for e in scope.find_elements(By.TAG_NAME, 'button') if e.is_displayed() and re.search(r'log\s*in|sign\s*in|লগইন', e.text, re.I)]
        # ResellKori has both a Login tab and a Login submit button, outside a
        # form. The tab merely selects a panel; it does not authenticate.
        if self.site == 'resellkori':
            submit = [e for e in submit if e.text.strip() == 'লগইন করুন']
        if not submit:
            submit = [e for e in scope.find_elements(By.CSS_SELECTOR, 'button[type="submit"],input[type="submit"]') if e.is_displayed()] if forms else []
        if not submit:
            raise CollectionStopped('A normal login button was not found. No alternative authentication endpoint was attempted.')
        self.check()
        submit[0].click()
        try:
            WebDriverWait(self.driver, 20).until(lambda d: not any(e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, 'input[type="password"]')))
        except TimeoutException:
            self.challenge()
            raise CollectionStopped('Supplier sign-in was not accepted. Check credentials, membership or verification in the supplier account.') from None
        self.safe_url(self.driver.current_url)
        if self.site == 'selfshop':
            self.phase = 'confirming SelfShop sign-in'
            WebDriverWait(self.driver, 20).until(lambda d: self.dom(
                "return [...document.querySelectorAll('a[href=\"/dashboard/settings\"]')].some(e=>/^Hello,/.test(e.textContent.trim()) && !e.textContent.includes('Sign in'))"))

    def checkpoint(self, page, message):
        self.check()
        SupplierJob.objects.using(DB).filter(pk=self.job.pk).update(payload={'site': self.site, 'checkpoint': page, 'pages': self.pages},
            counts=dict(self.counts), processed=len(self.seen) if self.site == 'business_koro' else sum(self.counts[k] for k in ('new','existing','updated','conflict','failed')),
            activity=message[:300], updated_at=timezone.now())
        self.report(f'{self.site}: {self.pages} pages; {self.counts["new"]} new, {self.counts["existing"]} existing, {self.counts["updated"]} updated, {self.counts["failed"]} failed', flush=True)

    def capture(self, items, page, category='', vendor='not-provided'):
        self.check()
        if self.pages >= self.max_pages:
            raise CollectionLimitReached('Configured page limit reached. Collected rows are saved, but catalogue completion is not claimed.')
        self.pages += 1
        if self.site == 'business_koro':
            from .business_koro_catalogue import observe_card
            for item in items:
                key = (item.get('url'), item.get('title'))
                if key in self.seen:
                    self.counts['duplicate_on_source'] += 1; continue
                self.seen.add(key)
                self.check()
                try: self.counts[observe_card(self.job.supplier, item, self.job.actor_id)] += 1
                except ValueError: self.counts['invalid_skipped'] += 1
            self.checkpoint(page, f'Reading reseller buying-price cards: {len(self.seen)} observations; membership gates are not bypassed')
            return
        for item in items:
            if item.get('title') and re.search(r'[\ud800-\udfff]', item['title']):
                # Source-side JavaScript substring can split an emoji in half.
                # Match the browser's replacement glyph, retain the product ID,
                # and flag this observation instead of dropping the entire row.
                item = dict(item, title=re.sub(r'[\ud800-\udfff]', '\ufffd', item['title']))
                self.counts['source_title_unicode_repaired'] += 1
            if not item.get('title'):
                self.counts['invalid_skipped'] += 1; continue
            if RESTRICTED.search(item['title']):
                self.counts['restricted_skipped'] += 1; continue
            if self.site == 'resellkori':
                # Its card usually displays estimated profit; occasional cards
                # display retail service prices. Neither proves source cost.
                item = dict(item, price=None)
            row = row_for(item, page, category, vendor)
            key = (row['external_id'], row['variant_id'], vendor)
            if key in self.seen:
                self.counts['duplicate_on_source'] += 1; continue
            self.seen.add(key)
            serializer = SnapshotSerializer(data=row)
            if not serializer.is_valid():
                self.counts['invalid_skipped'] += 1; continue
            from json import loads, dumps
            valid = loads(dumps(serializer.validated_data, default=str))
            try:
                self.check()
                if self.fill_missing_categories and valid['identity'].get('category'):
                    from .models import SupplierOffer
                    with transaction.atomic(using=DB):
                        old = SupplierOffer.objects.using(DB).select_for_update().filter(supplier=self.job.supplier,
                            external_id=valid['external_id'],variant_id=valid['variant_id'],
                            vendor_id=valid['vendor_id'],warehouse_id=valid['warehouse_id']).first()
                        without_category = {k:v for k,v in valid['identity'].items() if k != 'category'}
                        if old and not old.identity.get('category') and old.identity == without_category and old.title == valid['title']:
                            old.identity = dict(old.identity, category=valid['identity']['category'])
                            if old.current_decision_id and old.state == 'ready':
                                old.state = 'needs_review'
                            old.save(using=DB, update_fields=['identity','state','updated_at'])
                            audit('source_category_observed',supplier=self.job.supplier,offer=old,
                                category=valid['identity']['category'],observed_at=valid['observed_at'])
                            self.counts['category_enriched'] += 1
                outcome = snapshot_row(self.job.supplier, valid)
                if outcome == 'existing' and self.fill_missing_prices and valid['source_price'] is not None:
                    # Explicit opt-in enrichment only: never replace an existing
                    # known price, identity, content or manually edited shop data.
                    from .models import SupplierOffer
                    with transaction.atomic(using=DB):
                        old = SupplierOffer.objects.using(DB).select_for_update().get(supplier=self.job.supplier,
                            external_id=valid['external_id'], variant_id=valid['variant_id'],
                            vendor_id=valid['vendor_id'], warehouse_id=valid['warehouse_id'])
                        if old.source_price is None:
                            outcome = snapshot_row(self.job.supplier, valid, update=True)
                self.counts[outcome] += 1
                if row['source_price'] is None:
                    self.counts['unconfirmed_price'] += 1
            except (ValueError, ValidationError, IntegrityError) as exc:
                # Propagate cancellation/security changes; never log raw browser exceptions.
                if isinstance(exc, CollectionStopped):
                    raise
                self.counts['failed'] += 1
        self.checkpoint(page, f'Reading authorised catalogue: {self.pages} pages, {len(self.seen)} distinct identities')

    def dom(self, script, *args):
        return self.driver.execute_script(script, *args)

    def next_links(self):
        links = self.dom("return [...document.querySelectorAll('a')].filter(a=>/Next|পরবর্তী/.test(a.textContent)||a.rel==='next').filter(a=>!a.hasAttribute('disabled')&&!a.closest('.disabled')&&/^https?:/.test(a.href)).map(a=>a.href)")
        return list(dict.fromkeys(self.safe_url(u) for u in links if urlparse(u).hostname.removeprefix('www.') == self.allowed_host))

    def click_next_button(self):
        for attempt in range(3):
            self.check()
            if self.site=='business_koro':self.dismiss_business_koro_prompts()
            try:
                buttons = [e for e in self.driver.find_elements(By.XPATH,"//button[normalize-space()='Next']")
                           if e.is_displayed() and e.is_enabled()]
                if not buttons:
                    return False
                self.driver.execute_script('arguments[0].scrollIntoView({block:"center"})',buttons[0])
                buttons[0].click()
                return True
            except StaleElementReferenceException:
                continue
        raise CollectionStopped('Supplier pagination changed repeatedly during navigation; retry from the saved identities.')

    def dismiss_business_koro_prompts(self):
        # Non-binding app/notification prompts can cover the Next button.
        # Dismiss normally, without enabling notifications or forcing clicks.
        for button in self.driver.find_elements(By.TAG_NAME,'button'):
            try:
                if button.is_displayed() and button.text.strip() in ('পরে','বন্ধ করুন','Later','Close'):
                    button.click()
            except StaleElementReferenceException:continue

    def business_koro(self):
        self.goto(self.origin + self.start)
        self.dismiss_business_koro_prompts()
        previous = None
        while True:
            WebDriverWait(self.driver, 25).until(lambda d: self.dom("return /Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+\\d+\\s+products/.test(document.body.innerText) && document.querySelectorAll('a.group h3').length > 0"))
            counter=re.search(r'Showing\s+\d+\s+to\s+\d+\s+of\s+(\d+)\s+products',self.driver.find_element(By.TAG_NAME,'body').text)
            if counter:self.counts['browser_reported_total']=int(counter.group(1))
            signature = self.dom("return [...document.querySelectorAll('a.group h3')].map(h=>h.textContent.trim()).join('|')")
            if signature == previous:
                raise CollectionStopped('Catalogue page repeated; completion is not claimed.')
            items = self.dom("""return [...document.querySelectorAll('a.group')].filter(a=>a.querySelector('h3')).map(a=>{
              const buying=[...a.querySelectorAll('span')].find(s=>['আপনার পাইকারি মূল্য','Your wholesale price'].includes(s.textContent.trim()));
              return {url:a.href,title:a.querySelector('h3').textContent.trim(),
                image:a.querySelector('img')?.currentSrc||a.querySelector('img')?.src||null,
                price:buying?.parentElement?.querySelector('span:last-child')?.textContent?.trim()||null,
                price_label:buying?.textContent.trim()||null,access_required:new URL(a.href).pathname==='/dashboard/membership',
                stock_text:a.querySelector('.relative span')?.textContent.trim()||null};});""")
            self.capture(items, self.driver.current_url)
            previous = signature
            if not self.click_next_button(): break
            WebDriverWait(self.driver, 25).until(lambda d: self.dom("return [...document.querySelectorAll('a.group h3')].map(h=>h.textContent.trim()).join('|')", ) != signature)
        if self.counts.get('browser_reported_total')!=len(self.seen):
            self.warnings.append(f'Browser counter reports {self.counts.get("browser_reported_total")} products; {len(self.seen)} distinct visible cards were observed. Hidden/missing cards were not invented.')

    def shopbase(self):
        self.goto(self.origin + self.start)
        WebDriverWait(self.driver, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'a[href*="/store/products/"]'))
        cats = self.dom("return [...document.querySelectorAll('a')].filter(a=>/\\/store\\/products\\/\\d+\\/1$/.test(a.href)).map(a=>({url:a.href,name:a.textContent.trim(),text:a.parentElement.textContent.trim()}))")
        for cat in cats:
            # Empty categories still need one inspection: counts are informational, not authoritative inventory.
            current, visited = cat['url'], set()
            while current and current not in visited:
                visited.add(current); self.goto(current)
                items = self.dom("return [...document.querySelectorAll('.product-part')].map(e=>({id:e.querySelector('button.favorite')?.dataset.id,variant:'catalogue-type-'+(e.querySelector('button.favorite')?.dataset.type||'unknown'),title:e.querySelector('.product-name')?.textContent||'',price:e.querySelector('.price-td')?.textContent||null}))")
                for item in items:
                    item['url'] = current + '#product-' + str(item.get('id') or '')
                self.capture(items, current, cat['name'])
                current = next(iter(self.next_links()), None)
        if not cats:
            raise CollectionStopped('No ShopBase category index was available after normal sign-in.')

    def dropbazar(self):
        self.goto(self.origin + self.start)
        roots = self.dom("return [...document.querySelectorAll('a')].filter(a=>a.textContent.trim()==='সব দেখুন').map(a=>({url:a.href,name:(a.parentElement.querySelector('h2')?.textContent||'').replace(/\\(\\d+\\)\\s*$/,'').trim()}))")
        for root in roots:
            current, visited = root['url'], set()
            while current and current not in visited:
                visited.add(current); self.goto(current)
                items = self.dom("return [...document.querySelectorAll('a')].filter(a=>a.querySelector('.store-product-title')).map(a=>({url:a.href,title:a.querySelector('.store-product-title').textContent.trim(),price:a.querySelector('.store-price-main')?.textContent||null}))")
                self.capture(items, current, root['name'])
                current = next(iter(self.next_links()), None)
        if not roots:
            raise CollectionStopped('DropBazar category index was not available after normal sign-in.')

    def dropify(self):
        self.goto(self.origin + self.start)
        WebDriverWait(self.driver, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, '.product-card'))
        expected = re.search(r'of\s+([\d,]+)\s+products', self.driver.find_element(By.TAG_NAME, 'body').text, re.I)
        expected = int(expected.group(1).replace(',', '')) if expected else None
        while True:
            count = len(self.driver.find_elements(By.CSS_SELECTOR, '.product-card'))
            items = self.dom("return [...document.querySelectorAll('a[href*=\"/product/\"]')].filter(a=>a.querySelector('.product-name')).map(a=>({url:a.href,title:a.querySelector('.product-name').textContent,price:a.querySelector('.price-wholesale')?.textContent||null,stock:a.querySelector('.stock-badge.in-stock')?'in_stock':a.querySelector('.stock-badge.out-of-stock')?'out_of_stock':'unconfirmed'}))")
            self.capture(items, self.driver.current_url)
            if expected is not None and count >= expected:
                break
            self.dom('window.scrollTo(0,document.body.scrollHeight)')
            try:
                WebDriverWait(self.driver, 12).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '.product-card')) > count)
            except TimeoutException:
                if expected is not None and count < expected:
                    raise CollectionStopped(f'Supplier stopped loading after {count} of {expected} displayed products; partial collection retained.') from None
                break

    def dropshipping(self):
        self.goto(self.origin + self.start)
        WebDriverWait(self.driver, 30).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'tbody tr small'))
        if self.fill_missing_categories:
            control = next((e for e in self.driver.find_elements(By.TAG_NAME,'select')
                            if Select(e).options and Select(e).options[0].text.strip().casefold() == 'select category'), None)
            if not control:
                raise CollectionStopped('The visible category selector is unavailable; no categories were guessed.')
            scopes = [(e.get_attribute('value'),e.text.strip()) for e in Select(control).options if e.get_attribute('value')]
            for value, category in scopes:
                self.check()
                before = self.dropshipping_signature()
                control = next(e for e in self.driver.find_elements(By.TAG_NAME,'select')
                               if Select(e).options and Select(e).options[0].text.strip().casefold() == 'select category')
                Select(control).select_by_value(value)
                try:
                    WebDriverWait(self.driver,25).until(lambda d:self.dropshipping_signature() != before)
                    WebDriverWait(self.driver,25).until(lambda d:d.find_elements(By.CSS_SELECTOR,'tbody tr small') or re.search(r'no (?:data|products?|matching|records?)',d.find_element(By.TAG_NAME,'body').text,re.I))
                except TimeoutException:
                    self.warnings.append(f'Category {category}: source filter did not finish loading; category coverage remains incomplete.')
                    continue
                self.counts['category_scopes'] += 1
                self.dropshipping_pages(category)
            return
        # Resume through the site's visible page controls, never guessed API
        # URLs. The earlier committed pages remain in the database/audit.
        while True:
            current = self.dom("return Number(document.querySelector('.page-item.active')?.textContent.replace(/[^0-9]/g,''))")
            if current == self.start_page:
                break
            pages = self.dom("return [...document.querySelectorAll('.page-item:not(.disabled) a.page-link')].map(e=>Number(e.textContent.trim())).filter(n=>n>0)")
            targets = [n for n in pages if current < n <= self.start_page]
            if not targets:
                raise CollectionStopped('Requested resume page is not reachable through the visible pagination controls.')
            target = max(targets)
            self.check()
            self.driver.find_element(By.XPATH, f"//a[contains(@class,'page-link') and normalize-space()='{target}']").click()
            WebDriverWait(self.driver, 25).until(lambda d: self.dom("return Number(document.querySelector('.page-item.active')?.textContent.replace(/[^0-9]/g,''))") == target)
        self.dropshipping_pages()

    def dropshipping_signature(self):
        return self.dom("return JSON.stringify({ids:[...document.querySelectorAll('tbody tr small')].map(e=>e.textContent),lastPage:Math.max(0,...[...document.querySelectorAll('a.page-link')].map(e=>Number(e.textContent.trim())).filter(n=>n>0))})")

    def dropshipping_pages(self, category=''):
        while True:
            # JSON escapes malformed source Unicode instead of letting a bad
            # title abort Selenium's entire structured-result serialization.
            items = json.loads(self.dom("return JSON.stringify([...document.querySelectorAll('tbody tr')].filter(r=>r.querySelector('small')).map(r=>({id:r.querySelector('small').textContent.trim(),url:r.querySelector('a[href*=\"/product/\"]')?.href,title:r.querySelector('a[href*=\"/product/\"]')?.childNodes[0]?.textContent?.trim()||'',price:r.querySelectorAll('td')[3]?.textContent.match(/Dropshipper Price\\s*:\\s*([\\d,.]+)/)?.[1]||null})))"))
            self.capture(items, self.driver.current_url, category=category)
            buttons = self.driver.find_elements(By.CSS_SELECTOR, 'a.page-link')
            nxt = next((a for a in buttons if 'Next' in a.text and 'disabled' not in a.find_element(By.XPATH,'..').get_attribute('class')), None)
            if not nxt:
                break
            if not items:
                self.warnings.append(f'Category {category or "all"}: empty rows with enabled pagination; source coverage requires review.')
                break
            before = self.dropshipping_signature()
            nxt.click()
            WebDriverWait(self.driver, 25).until(lambda d: d.find_elements(By.CSS_SELECTOR,'tbody tr small') and self.dropshipping_signature() != before)

    def uddoog(self):
        self.goto(self.origin + self.start)
        WebDriverWait(self.driver, 25).until(lambda d: d.find_elements(By.CSS_SELECTOR,'label input[type="checkbox"]'))
        count_before = 0
        while True:
            # Read the library only. Never tick product/store checkboxes or press Add.
            items = self.dom("return [...document.querySelectorAll('div[class*=\"overflow-y-auto\"] label')].filter(e=>e.querySelector('input[type=\"checkbox\"]')&&e.querySelector('img')).map(e=>({title:e.querySelector('img').alt,image:e.querySelector('img').src}))")
            for item in items:
                item['id'] = 'catalogue-' + hashlib.sha256((item['title']+'\n'+item['image']).encode()).hexdigest()[:48]
                item['url'] = self.driver.current_url + '#' + item['id']
                item['price'] = None  # UI range/suggested price is NOT a confirmed supplier cost.
            self.capture(items, self.driver.current_url)
            if len(items) <= count_before:
                break
            count_before = len(items)
            self.dom("let e=document.querySelector('div[class*=\"overflow-y-auto\"]');if(e)e.scrollTo(0,e.scrollHeight)")
            try:
                WebDriverWait(self.driver, 8).until(lambda d: len(d.find_elements(By.CSS_SELECTOR,'div[class*="overflow-y-auto"] label img')) > count_before)
            except TimeoutException:
                break
        self.warnings.append('Visible library collected, but no complete master-catalogue pagination or source-cost feed was exposed. API/store approval is still required for full coverage.')

    def selfshop(self):
        self.goto(self.origin + self.start)
        WebDriverWait(self.driver, 25).until(lambda d: d.find_elements(By.CSS_SELECTOR,'a[href*="/supplier/"]'))
        vendor_urls, directory_pages = [], 0
        while True:
            urls = self.dom("return [...document.querySelectorAll('a[href*=\"/supplier/\"]')].map(a=>a.href)")
            for url in urls:
                if url not in vendor_urls:
                    vendor_urls.append(url)
            directory_pages += 1
            if directory_pages > 100:
                raise CollectionStopped('Vendor-directory page safety limit reached; partial collection requires review.')
            self.counts['vendor_directory_pages'] = directory_pages
            self.checkpoint(self.driver.current_url, f'Reading vendor directory: {directory_pages} pages, {len(vendor_urls)} vendors')
            before = urls[0] if urls else None
            if not self.click_next_button():
                break
            WebDriverWait(self.driver, 20).until(lambda d: self.dom("return document.querySelector('a[href*=\"/supplier/\"]')?.href||null") not in (None,before))
        self.counts['vendor_directory_pages'] = directory_pages
        for url in vendor_urls:
            self.goto(url)
            vendor = urlparse(url).path.rstrip('/').split('/')[-1][:120]
            ready = False
            for attempt in range(2):
                try:
                    WebDriverWait(self.driver, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR,'a[href*="/product/"] h3') or re.search(r'All Products\s*\(\s*0\s*\)|No products available yet',d.find_element(By.TAG_NAME,'body').text,re.I))
                    ready = True
                    break
                except TimeoutException:
                    self.challenge()
                    if attempt == 0:
                        self.goto(self.driver.current_url)
            if not ready:
                self.warnings.append(f'Vendor {vendor}: catalogue not ready; retry required.')
                continue
            expected_match = re.search(r'All Products\s*\(\s*(\d+)\s*\)', self.driver.find_element(By.TAG_NAME,'body').text, re.I)
            expected = int(expected_match.group(1)) if expected_match else None
            categories = self.dom("let all=[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='All'&&e.getClientRects().length);return all?[...all.parentElement.querySelectorAll('button')].map(e=>e.textContent.trim()).filter(s=>s&&!['All','All Products','Profile'].includes(s)):[]")
            # A vendor with one source category unambiguously classifies all
            # its cards. Multiple-category vendors remain unconfirmed here.
            category = categories[0] if len(categories) == 1 else ''
            vendor_seen, old_signature = set(), None
            while True:
                items = self.dom("return [...document.querySelectorAll('a[href*=\"/product/\"]')].filter(a=>a.querySelector('h3')).map(a=>({url:a.href,title:a.querySelector('h3').textContent,price:a.parentElement.querySelector('.digit-font')?.textContent||null}))")
                self.capture(items, self.driver.current_url, category=category, vendor=vendor)
                vendor_seen.update(x['url'] for x in items)
                if expected is not None and len(vendor_seen) >= expected:
                    break
                signature = '|'.join(x['url'] for x in items)
                if signature == old_signature:
                    self.warnings.append(f'Vendor {vendor}: repeated pagination detected; stopped safely.')
                    break
                old_signature = signature
                if not self.click_next_button():
                    if expected is not None and len(vendor_seen) < expected:
                        self.warnings.append(f'Vendor {vendor}: only {len(vendor_seen)} of {expected} listed products were exposed.')
                    break
                try:
                    WebDriverWait(self.driver, 20).until(lambda d: self.dom("return [...document.querySelectorAll('a[href*=\"/product/\"]')].filter(a=>a.querySelector('h3')).map(a=>a.href).join('|')") not in ('',signature))
                except TimeoutException:
                    # Retry the already selected page through its visible URL.
                    # Never skip ahead or mark a timeout as confirmed no stock.
                    self.goto(self.driver.current_url)
                    try:
                        WebDriverWait(self.driver,20).until(lambda d:self.dom("return [...document.querySelectorAll('a[href*=\"/product/\"]')].filter(a=>a.querySelector('h3')).map(a=>a.href).join('|')") not in ('',signature))
                    except TimeoutException:
                        self.warnings.append(f'Vendor {vendor}: next page did not load after retry; retry required.')
                        break
        if not vendor_urls:
            raise CollectionStopped('No vendor directory was available; no complete SelfShop catalogue claim can be made.')

    def resellkori(self):
        self.goto(self.origin + self.start)
        WebDriverWait(self.driver, 30).until(lambda d: d.find_elements(By.CSS_SELECTOR,'h3.wd-entities-title a'))
        offset = 0
        while True:
            items = self.dom("return [...document.querySelectorAll('.product-grid-item')].slice(arguments[0]).map(e=>{let a=e.querySelector('h3.wd-entities-title a');return {id:e.querySelector('[data-product_id]')?.getAttribute('data-product_id')||null,url:a?.href,title:a?.textContent||'',category:e.querySelector('.wd-product-cats a')?.textContent.trim()||'',price:null}})", offset)
            self.capture(items, self.driver.current_url)
            count = self.dom("return document.querySelectorAll('.product-grid-item').length")
            more = [e for e in self.driver.find_elements(By.CSS_SELECTOR,'a.wd-products-load-more') if e.is_displayed()]
            if not more:
                break
            offset = count
            # Catalogue Load More only. Never click any cart, order or wishlist action.
            self.driver.execute_script('arguments[0].scrollIntoView({block:"center"})', more[0])
            more[0].click()
            try:
                WebDriverWait(self.driver, 25).until(lambda d: self.dom("return document.querySelectorAll('.product-grid-item').length") > count or not any(e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR,'a.wd-products-load-more')))
            except TimeoutException:
                raise CollectionStopped('ResellKori Load More did not progress. Partial identities retained; no hidden endpoint was used.') from None

    def run(self):
        # Selenium wire-level DEBUG logs contain send_keys payloads. Never allow
        # authentication values or DOM payloads into Django/driver logs.
        for name in ('selenium', 'selenium.webdriver.remote.remote_connection',
                     'selenium.webdriver.common.selenium_manager', 'urllib3', 'urllib3.connectionpool'):
            logging.getLogger(name).setLevel(logging.WARNING)
        options = ChromeOptions() if self.use_browser_profile else Options() if os.name == 'nt' else ChromeOptions()
        if self.use_browser_profile:
            profile = Path(settings.BASE_DIR) / 'private_suppliers' / 'browser_profiles' / self.site
            options.add_argument('--user-data-dir=' + str(profile))
        if self.headless:
            options.add_argument('--headless=new')
        options.add_argument('--window-size=1360,1000')
        # No stealth, personal profile, certificate override, proxy or authentication bypass.
        try:
            if self.use_browser_profile and not profile.is_dir():
                raise CollectionStopped('Open the dedicated Chrome profile and sign in before collecting.')
            self.driver = webdriver.Chrome(options=options) if self.use_browser_profile or os.name != 'nt' else webdriver.Edge(options=options)
            self.driver.set_page_load_timeout(40)
            self.login()
            self.password = ''
            self.phase = 'reading product catalogue'
            method = getattr(self, self.site, None)
            if not method:
                raise CollectionStopped('This catalogue parser is not mapped yet; no unsupported internal API was requested.')
            method()
            self.job.refresh_from_db(using=DB)
            self.job.counts = dict(self.counts)
            if self.counts['source_title_unicode_repaired']:
                self.warnings.append(f'{self.counts["source_title_unicode_repaired"]} source table titles had split Unicode characters. Browser replacement glyph retained; verify full source titles before exact matching/import.')
            self.job.errors = [{'message': w} for w in self.warnings[:100]]
            self.job.processed = self.job.total = len(self.seen) if self.site == 'business_koro' else sum(self.counts[k] for k in ('new','existing','updated','conflict','failed'))
            state = 'completed_with_errors' if self.counts['failed'] or self.counts['invalid_skipped'] or self.warnings else 'completed'
            scope = f' from source page {self.start_page}' if self.start_page > 1 else ''
            finish(self.job, state, f'Browser catalogue traversal finished: {self.pages} pages{scope}; no filtering, publication or orders performed.')
        except KeyboardInterrupt:
            self.job.refresh_from_db(using=DB)
            finish(self.job, 'cancelled', 'Collector interrupted; saved identities retained.')
            raise
        except CollectionLimitReached as exc:
            self.job.refresh_from_db(using=DB)
            self.job.errors = [{'message':str(exc)}]
            finish(self.job, 'completed_with_errors', str(exc))
            self.report(f'{self.site}: {exc}', flush=True)
        except Exception as exc:
            self.job.refresh_from_db(using=DB)
            code = re.search(r'net::ERR_[A-Z_]+', str(exc))
            message = str(exc)[:260] if isinstance(exc, CollectionStopped) else f'{type(exc).__name__} during {self.phase}' + (f' ({code.group()})' if code else '') + '. Partial collection retained; no access bypass attempted.'
            finish(self.job, 'cancelled' if self.job.status == 'cancel_requested' else 'failed', message)
            self.report(f'{self.site}: {message}', flush=True)
        finally:
            self.password = ''
            if self.driver:
                try:
                    self.driver.quit()
                except WebDriverException:
                    pass
