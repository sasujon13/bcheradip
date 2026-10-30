"""Read the owner's eight buying-price widgets through normal browser pages."""
import copy
import logging
from decimal import Decimal
from urllib.parse import urlsplit
from lxml import html
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from django.db import close_old_connections, transaction
from django.utils import timezone

from .supplier_browser import BrowserCollector, CollectionStopped, start_job
from .price_ensure import SAMPLES, extract_buying_price, collected_amount
from .models import Supplier, SupplierSourceProduct, SupplierOffer, Product, ProductVariant, DeliverySettings
from .supplier_crypto import decrypt

DB = 'ecommerce'
VERSION = 'visible-buying-price-v2'
SELECTORS = {
    'resellkori': ('css', '.reselling-price-btn', 'Reseller Price'),
    'shopbase': ('xpath', "//button[contains(.,'প্রাইস')][.//span[contains(@class,'text-danger')]]", 'প্রাইস'),
    'dropbazar': ('xpath', "//button[contains(.,'প্রাইস')][.//span[contains(@class,'text-danger')]]", 'প্রাইস'),
    'business_koro': ('xpath', "//span[span[normalize-space()='আপনার পাইকারি মূল্য']][b]", 'আপনার পাইকারি মূল্য'),
    'dropify': ('css', '.pd-price-item:has(.wholesale)', 'Wholesale Price'),
    'uddoog': ('xpath', "//dt[normalize-space()='Base']/..", 'Base'),
    'selfshop': ('xpath', "//span[normalize-space()='Price :']/..", 'Price'),
    'dropshipping': ('xpath', "//span[@id='variant_wise_price'][contains(.,'ড্রপশিপার প্রাইজ')]", 'ড্রপশিপার প্রাইজ'),
}


def clean_fragment(markup):
    """Keep the actual price DOM, excluding links, scripts and hidden input data."""
    root = html.fromstring(markup)
    for node in list(root.iter()):
        if node.tag in ('script', 'style', 'input', 'iframe'):
            node.drop_tree()
            continue
        for key in list(node.attrib):
            if key not in ('class', 'id'):
                del node.attrib[key]
    return html.tostring(root, encoding='unicode')[:12000]


def read_price_widget(driver, site):
    kind, selector, label = SELECTORS[site]
    by = By.CSS_SELECTOR if kind == 'css' else By.XPATH

    def ready(d):
        if site=='selfshop' and any(e.is_displayed() and e.text.strip()=='Product Not Found'
                for e in d.find_elements(By.TAG_NAME,'h2')):
            raise CollectionStopped('Supplier reports Product Not Found; previous buying price retained.')
        nodes = [n for n in d.find_elements(by, selector) if n.is_displayed()]
        prices = []
        for node in nodes:
            fragment = node.get_attribute('outerHTML')
            price, extracted_label = extract_buying_price(site, fragment)
            if price and Decimal(price) > 0 and extracted_label == label:
                prices.append((price, clean_fragment(fragment)))
        if prices and len({p[0] for p in prices}) == 1:
            return prices[0]
        return False

    price, fragment = WebDriverWait(driver, 25).until(ready)
    return {'amount': price, 'label': label, 'selector_type': kind, 'selector': selector,
            'html': fragment, 'mapping_version': VERSION, 'checked_at': timezone.now().isoformat()}


def collect_uddoog_reference(driver, url, evidence):
    """Explicit one-product collection, separate from Ensure Price's read-only check."""
    import hashlib
    from .models import SupplierRecollectionRun
    from .supplier_recollection import save_record, MAPPING_VERSION
    slug=urlsplit(url).path.rstrip('/').split('/')[-1]
    existing=SupplierSourceProduct.objects.using(DB).filter(supplier_id=3,url__endswith='/'+slug).first()
    if existing:
        return existing
    heading=driver.find_element(By.TAG_NAME,'h1')
    title=heading.text.strip()
    section=heading.find_element(By.XPATH,'..')
    description=section.find_element(By.CSS_SELECTOR,'.prose-storefront').get_attribute('innerHTML')
    images=[{'url':i.get_attribute('src'),'role':'main' if n==0 else 'gallery','alt':title} for n,i in
        enumerate(driver.find_elements(By.XPATH,'//img[@alt='+repr(title)+']'))]
    if not images or not description:
        raise CollectionStopped('Reference product lacks its own description or original image; collection needs review.')
    external='browser-url-'+hashlib.sha256(url.encode()).hexdigest()[:48]
    run=SupplierRecollectionRun.objects.using(DB).create(supplier_id=3,mode='inspect',status='running',
        mapping_version=MAPPING_VERSION,coverage={'method':'normal signed-in browser reference product','scope':url})
    record={'external_id':external,'url':url,'title':title,'description':description,'media':images,
        'prices':{'base_price':{'amount':evidence['amount'],'currency':'BDT','source_label':'Base'}},
        'stock':{'status':'in_stock' if 'In stock' in section.text else 'unconfirmed'},
        'extra':{'identity_origin':'browser_url','browser_preferred':True,'buying_price_verification':evidence},
        'raw_data':{'description_html':description,'buying_price_html':evidence['html']}}
    save_record(run.pk,record)
    run.status='completed';run.finished_at=timezone.now();run.save(using=DB)
    return SupplierSourceProduct.objects.using(DB).get(supplier_id=3,external_id=external)


@transaction.atomic(using=DB)
def save_selfshop_price(source_id, evidence):
    """Correct buying cost and unchanged generated selling prices; preserve stock/orders."""
    from .supplier_service import costs_for, audit
    from .pricing import calculate_price, retail_prices
    source = SupplierSourceProduct.objects.using(DB).select_for_update().get(pk=source_id, supplier_id=4)
    cost = Decimal(evidence['amount'])
    previous = (source.prices.get('storefront_price') or {}).get('amount')
    source.prices = {**source.prices,
        'storefront_price': {'amount': str(cost), 'currency': 'BDT', 'source_label': 'Price',
                             'source_url': source.url, 'checked_at': evidence['checked_at']},
        'buying_basis': 'Owner-confirmed visible Price; ProductResellerPrice and internal wholesale are not payable cost.'}
    source.extra = {**source.extra, 'buying_price_verification': evidence}
    source.save(using=DB, update_fields=['prices', 'extra', 'updated_at'])
    changed = repriced = manual = 0
    rules = DeliverySettings.current().pricing_rules
    for offer in SupplierOffer.objects.using(DB).select_for_update().filter(source_product=source):
        # Variant-specific quotes require their own visible price evidence.
        if offer.variant_id and source.variants and any(
                str(v.get('price') or v.get('sale_price') or cost) != str(cost)
                for v in source.variants if isinstance(v, dict)):
            continue
        if offer.source_price != cost:
            offer.source_price = cost
            offer.save(using=DB, update_fields=['source_price', 'updated_at'])
            changed += 1
        if not offer.imported_product_id:
            continue
        product = Product.objects.using(DB).select_for_update().get(pk=offer.imported_product_id)
        for variant in ProductVariant.objects.using(DB).select_for_update().filter(product=product):
            old = (product.attributes.get('_retail_pricing') or {}).get(str(variant.pk), {})
            variant.cost_price = cost
            fields = ['cost_price', 'updated_at']
            if old.get('applied_price') is not None and variant.price == Decimal(old['applied_price']):
                costs = costs_for(offer)
                base = calculate_price(cost, {k: str(costs[k]) for k in
                    ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs')},
                    subsidy_enabled=False, rules=rules)['suggested_price']
                pair = retail_prices(base, rules)
                mode = old.get('mode', 'sale')
                variant.price = Decimal(pair['regular_price'] if mode == 'reserve' else pair['sale_price'])
                variant.compare_at_price = Decimal(pair['regular_price']) if mode == 'sale' else None
                pair.update(mode=mode, applied_price=str(variant.price), updated_at=timezone.now().isoformat())
                product.attributes = {**product.attributes, '_retail_pricing': {
                    **product.attributes.get('_retail_pricing', {}), str(variant.pk): pair}}
                product.save(using=DB, update_fields=['attributes', 'updated_at'])
                fields += ['price', 'compare_at_price']
                repriced += 1
            else:
                manual += 1
            variant.save(using=DB, update_fields=fields)
    audit('selfshop_visible_buying_price_checked', supplier=source.supplier,
          source_id=source.pk, previous=previous, buying_price=str(cost), offers_changed=changed,
          generated_prices_refreshed=repriced, manual_prices_preserved=manual,
          accepted_orders_unchanged=True, mapping_version=VERSION)
    return {'offers_changed': changed, 'repriced': repriced, 'manual_prices_preserved': manual}


class PriceProbe(BrowserCollector):
    def __init__(self, *args, targets, on_result=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.price_only = True
        self.targets, self.on_result, self.results = targets, on_result, []

    def probe(self):
        auth=urlsplit(self.driver.current_url)
        authenticated_origin=auth.scheme+'://'+auth.netloc
        self.job.total = len(self.targets)
        self.job.save(using=DB, update_fields=['total', 'updated_at'])
        controller=self.driver.current_window_handle
        prefetched={}
        prefetch=self.site=='selfshop' and len(self.targets)>8
        for index,target in enumerate(self.targets):
            self.check()
            if prefetch and index%4==0:
                # Four ordinary product tabs let the React pages finish
                # rendering together. Only one bounded browser is used.
                self.driver.switch_to.window(controller)
                for upcoming in self.targets[index:index+4]:
                    before=set(self.driver.window_handles)
                    self.driver.execute_script("window.open(arguments[0], '_blank');",
                        authenticated_origin+urlsplit(upcoming['url']).path)
                    handles=WebDriverWait(self.driver,10).until(lambda d:set(d.window_handles)-before)
                    prefetched[upcoming['url']]=next(iter(handles))
            row = {k: target[k] for k in ('site', 'url', 'label', 'price_property')}
            if target.get('source_id'):
                row['source_id']=target['source_id']
            row.update(reference=target.get('expected'), live=None, collected=None,
                       extraction_ok=False, ok=False, error='')
            row['collected']=collected_amount(target['url'],target['price_property'])
            try:
                # Keep the authenticated canonical host (www cookies are not
                # necessarily shared with the bare domain).
                if prefetch:
                    self.driver.switch_to.window(prefetched.pop(target['url']))
                    WebDriverWait(self.driver,25).until(lambda d:d.current_url!='about:blank' and d.find_elements(By.TAG_NAME,'body'))
                    self.safe_url(self.driver.current_url)
                    self.challenge()
                else:
                    self.goto(authenticated_origin + urlsplit(target['url']).path)
                from .supplier_visible_catalogue import canonical_url
                if canonical_url(self.driver.current_url) != canonical_url(target['url']):
                    raise CollectionStopped('The product redirected; no current product price was accepted.')
                evidence = read_price_widget(self.driver, self.site)
                close_old_connections()
                row.update(live=evidence['amount'], evidence=evidence, extraction_ok=True)
                row['collected_before'] = collected_amount(target['url'], target['price_property'])
                if self.site=='uddoog' and target.get('collect_reference') and row['collected_before'] is None:
                    collect_uddoog_reference(self.driver,target['url'],evidence)
                if target.get('source_id'):
                    row.update(save_selfshop_price(target['source_id'], evidence))
                row['collected'] = collected_amount(target['url'], target['price_property'])
                row['ok'] = bool(row['collected'] is not None and Decimal(str(row['collected'])) == Decimal(row['live']))
                self.counts['updated'] += 1
            except Exception as exc:
                # Selenium errors can contain DOM or session internals. Keep
                # only an actionable fixed reason and the exception category.
                row['error'] = str(exc) if isinstance(exc, CollectionStopped) else type(exc).__name__ + ': product price widget not readable; sign-in or page mapping needs review.'
                self.counts['failed'] += 1
            finally:
                if prefetch and self.driver.current_window_handle!=controller:
                    self.driver.close()
                    self.driver.switch_to.window(controller)
            self.results.append(row)
            if self.on_result:
                self.on_result(row)
            self.pages += 1
            self.seen.add(target['url'])
            self.checkpoint(target['url'], f'Buying prices: {len(self.results)}/{len(self.targets)} checked; {self.counts["failed"]} failures')

    selfshop = resellkori = shopbase = dropbazar = business_koro = dropify = uddoog = dropshipping = probe


def run_probe(site, targets, on_result=None):
    from pathlib import Path
    from django.conf import settings
    from .models import SupplierJob
    sample = next(s for s in SAMPLES if s['site'] == site)
    supplier = Supplier.objects.using(DB).get(pk=sample['supplier_id'])
    credentials = decrypt(supplier)
    try:
        if all(not t.get('source_id') for t in targets):
            # A bounded read-only probe does not mutate a catalogue worker's
            # checkpoint or wait for an unrelated identity import to finish.
            with transaction.atomic(using=DB):
                Supplier.objects.using(DB).select_for_update().get(pk=supplier.pk)
                if not supplier.enabled or not supplier.terms_confirmed:
                    raise CollectionStopped('Supplier access is paused or not approved.')
                if SupplierJob.objects.using(DB).filter(runner='browser',status__in=('queued','running','cancel_requested')).count()>=2:
                    raise CollectionStopped('Two browser jobs are active; retry this verification after one finishes.')
                job=SupplierJob.objects.using(DB).create(supplier=supplier,runner='browser',action='update',
                    status='running',activity='Reading one owner-approved buying-price widget',payload={'site':site,'scope':'price_probe'})
        else:
            job = start_job(site)
        use_profile=site=='resellkori' and (Path(settings.BASE_DIR)/'private_suppliers'/'browser_profiles'/site).is_dir()
        collector = PriceProbe(site, job, credentials.get('username', ''), credentials.get('password', ''),
                               targets=targets, on_result=on_result,use_browser_profile=use_profile)
        collector.run()
        if not collector.results:
            job.refresh_from_db(using=DB)
            raise CollectionStopped(job.activity)
        return collector.results
    finally:
        credentials.clear()
