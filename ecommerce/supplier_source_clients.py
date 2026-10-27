"""Fresh source traversal using observed first-party endpoints and ordinary sign-in.

No cart/order/store mutations, browser-session extraction, access bypass or TLS overrides.
"""
import json
import logging
import re
import time
from urllib.parse import urlencode, urljoin, urlsplit, unquote

import requests
from lxml import html

from . import supplier_source_parsers as parse
from .supplier_recollection import reference_url

ORIGINS = {'business_koro': 'https://www.businesskoro.com', 'shopbase': 'https://shopbasebd.com',
    'dropbazar': 'https://dropbazarbd.com', 'dropify': 'https://www.dropifybd.com',
    'selfshop': 'https://selfshop.com.bd', 'uddoog': 'https://dropshop.com.bd',
    'resellkori': 'https://resellkori.com', 'dropshipping': 'https://www.dropshipping.com.bd'}
SUPPLIER_IDS = {'business_koro': 2, 'shopbase': 1, 'dropbazar': 6, 'dropify': 7,
                'selfshop': 4, 'uddoog': 3, 'resellkori': 8, 'dropshipping': 9}


class SourceError(ValueError):
    pass


class SourceClient:
    def __init__(self, site, username='', password='', progress=lambda **kw: None, interval=.35, skip_ids=None, public_only=False):
        if site not in ORIGINS:
            raise SourceError('This supplier has no inspected source mapping.')
        self.site, self.origin = site, ORIGINS[site]
        self.username, self.password, self.progress = username, password, progress
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({'User-Agent': 'CheradipCatalogue/1.0', 'Accept': 'application/json,text/html'})
        self.allowed_hosts = {urlsplit(self.origin).hostname.removeprefix('www.')}
        if site == 'business_koro':
            self.allowed_hosts.add('api.businesskoro.com')
        if site == 'selfshop':
            self.allowed_hosts.add('api-v1.selfshop.com.bd')
        self.tokens = {}
        # SelfShop throttled the first public traversal after 65 observations.
        # A conservative <=40 requests/minute is ordinary backoff, not a second
        # identity, proxy or alternate-key route around a source quota.
        self.interval, self.last_request = max(interval, 1.5) if site == 'selfshop' else interval, 0
        self.expected_total = None
        self.skip_ids = set(skip_ids or ())
        self.public_only = public_only
        self.coverage = {'source': self.origin, 'method': 'fresh original-source traversal', 'access_gaps': []}
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    def close(self):
        self.password = ''
        self.tokens.clear()
        self.session.close()

    def request(self, url, *, method='GET', data=None, json_data=None, headers=None):
        network_retries = 0
        for redirect in range(5):
            reference_url(url)
            parts = urlsplit(url)
            if parts.hostname.removeprefix('www.') not in self.allowed_hosts:
                raise SourceError('Source attempted an unapproved destination; stopped.')
            if any(x in parts.query.lower() for x in ('add-to-cart', 'delete=', 'logout', 'checkout')):
                raise SourceError('Non-catalogue action refused.')
            self.progress(activity='Reading original source: ' + parts.path)
            gap = self.interval - (time.monotonic() - self.last_request)
            if gap > 0:
                time.sleep(gap)
            auth = self.tokens.get(parts.hostname)
            request_headers = {**(headers or {}), **({'Authorization': 'Bearer ' + auth} if auth else {})}
            try:
                response = self.session.request(method, url, data=data, json=json_data, headers=request_headers,
                    timeout=(10, 35), allow_redirects=False, stream=True)
                self.last_request = time.monotonic()
                if response.is_redirect:
                    target = urljoin(url, response.headers.get('Location', ''))
                    response.close()
                    url, method, data, json_data = target, 'GET', None, None
                    continue
                if response.status_code != 200:
                    status = response.status_code
                    response.close()
                    if method == 'GET' and status in (500,502,503,504) and network_retries < 2:
                        network_retries += 1
                        time.sleep(2 ** network_retries)
                        continue
                    raise SourceError(f'Source HTTP {status}; no timestamp or stock confirmation invented.')
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > 12 * 1024 * 1024:
                        raise SourceError('Source response exceeds the reviewed limit; no truncation accepted.')
                response._content = bytes(body)
                response._content_consumed = True
                response.close()
                return response
            except requests.RequestException as exc:
                # Bounded retries only for read-only requests interrupted by a
                # connection failure. Never retry sign-in, TLS certificate
                # failures, 401/403/429, or circumvent source access limits.
                if (method == 'GET' and network_retries < 2 and
                        isinstance(exc, (requests.Timeout, requests.ConnectionError)) and
                        not isinstance(exc, requests.exceptions.SSLError)):
                    network_retries += 1
                    time.sleep(2 ** network_retries)
                    continue
                raise SourceError('Source network/TLS request failed (' + type(exc).__name__ + '); saved checkpoints retained, no security bypass.') from None
        raise SourceError('Source redirect limit reached.')

    def login(self):
        if self.public_only:
            self.coverage['access_gaps'].append('Explicit public-only collection: buying prices and gated account data are not verified.')
            return
        if self.site == 'selfshop':
            if not self.username or not self.password:
                raise SourceError('Normal SelfShop account sign-in is required; public collection must be explicitly selected.')
            # The supplier's own login form posts the Phone Number field as
            # email, then uses the returned bearer token for product details.
            result = self.request('https://api-v1.selfshop.com.bd/api/login', method='POST',
                json_data={'email':self.username,'password':self.password}).json()
            if not result.get('status') or not isinstance(result.get('token'),str):
                raise SourceError('Normal SelfShop sign-in was not accepted.')
            self.tokens['api-v1.selfshop.com.bd'] = result['token']
            self.coverage['account_authenticated'] = True
            return
        if not self.username or not self.password:
            raise SourceError('Normal supplier login is required. Supply one-run credentials privately.')
        if self.site == 'uddoog':
            response = self.request(self.origin + '/api/v1/auth/dropshipper/login', method='POST',
                json_data={'email': self.username, 'password': self.password, 'role': 'dropshipper'}).json()
            data = response.get('data') or {}
            if response.get('success') is not True or not isinstance(data.get('token'), str):
                raise SourceError('Normal dropshipper login was not accepted.')
            self.tokens['dropshop.com.bd'] = data['token']
            self.coverage['account_authenticated'] = True
            return
        if self.site == 'dropshipping':
            page = self.request(self.origin + '/dropshipper/login')
            headers = {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json', 'Referer': page.url}
            # Ordinary Laravel XSRF cookie from this HTTP session, not extracted
            # browser credentials. The reseller API is different from /login.
            for cookie in self.session.cookies:
                if cookie.name == 'XSRF-TOKEN':
                    headers['X-XSRF-TOKEN'] = unquote(cookie.value)
            response = self.request(self.origin + '/api/reseller/login', method='POST',
                data={'phone': self.username, 'password': self.password}, headers=headers).json()
            if response.get('status') is not True or not response.get('reseller_token'):
                raise SourceError('Normal reseller login was not accepted.')
            self.coverage['account_authenticated'] = True
            return
        if self.site == 'business_koro':
            response = self.request('https://api.businesskoro.com/api/v1/auth/login', method='POST',
                json_data={'identifier': self.username, 'password': self.password}).json()
            if not isinstance(response.get('accessToken'), str):
                raise SourceError('Source did not accept the normal account login.')
            self.tokens['api.businesskoro.com'] = response['accessToken']
            return
        path = {'shopbase': '/store/login', 'dropbazar': '/login', 'dropify': '/dropshipper/login',
                'resellkori': '/login/', 'dropshipping': '/login'}[self.site]
        response = self.request(self.origin + path)
        doc = html.fromstring(response.content)
        if doc.xpath('//iframe[contains(@src,"captcha")]'):
            raise SourceError('Manual source CAPTCHA required; stopped.')
        if self.site == 'resellkori':
            scripts = '\n'.join(doc.xpath('//script[not(@src)]/text()'))
            found = re.search(r'(?:var\s+)?RKA\s*=\s*(\{[^;]+\})', scripts)
            if not found:
                raise SourceError('Normal source sign-in configuration is unavailable.')
            config = json.loads(found.group(1))
            result = self.request(config['ajax_url'], method='POST', data={'action': 'rka_login',
                'nonce': config['nonce'], 'username': self.username, 'password': self.password}).json()
            if result.get('success') is not True:
                raise SourceError('Source did not accept the normal account login.')
            return
        forms = doc.xpath('//form[.//input[@type="password"]]')
        if len(forms) != 1:
            raise SourceError('A unique normal supplier sign-in form is unavailable.')
        form = forms[0]
        payload = {e.get('name'): e.get('value', '') for e in form.xpath('.//input[@type="hidden"]') if e.get('name')}
        if self.site == 'shopbase':
            target = self.origin + '/store/logincheck'
            payload.update(username=self.username, password=self.password)
        else:
            target = urljoin(response.url, form.get('action') or response.url)
            payload.update(phone=self.username, password=self.password)
        result = self.request(target, method='POST', data=payload, headers={'Referer': response.url})
        if self.site == 'shopbase':
            if result.json().get('result') != 'success':
                raise SourceError('Source did not accept the normal account login.')
        elif html.fromstring(result.content).xpath('//form[.//input[@type="password"]]'):
            raise SourceError('Source returned the login form. Reconnect the account; no authenticated collection claimed.')

    def products(self):
        self.login()
        yield from getattr(self, self.site)()

    def detail_record(self, external_id, url, loader, **identity):
        try:
            return loader()
        except SourceError as exc:
            if re.search(r'HTTP (?:401|403|429)', str(exc)):
                raise  # Do not hammer a locked account or evade a quota/access limit.
            return {'external_id': str(external_id), 'url': url, **identity, '_error': str(exc)}
        except (ValueError, KeyError, TypeError):
            return {'external_id': str(external_id), 'url': url, **identity, '_error': 'Original product schema/content requires mapper review; no invented values.'}

    def business_koro(self):
        seen, signatures = set(), set()
        for page in range(1, 1001):
            data = self.request('https://api.businesskoro.com/api/v1/products?' + urlencode({'page': page, 'limit': 100})).json()
            products = data.get('data')
            if not isinstance(products, list):
                raise SourceError('Business Koro product schema changed.')
            self.expected_total = data.get('total')
            signature = tuple(str(p.get('id')) for p in products)
            if signature and signature in signatures:
                raise SourceError('Business Koro pagination repeated; not complete.')
            signatures.add(signature)
            for product in products:
                if product['id'] not in seen:
                    seen.add(product['id'])
                    if str(product['id']) in self.skip_ids:
                        continue
                    if product.get('locked'):
                        self.coverage['access_gaps'].append('Membership-locked product identity: ' + str(product['id']))
                        record = parse.business_koro(product, data.get('deliveryCharges'))
                        record['media'] = []
                        record['description'] = ''
                        record['extra']['content_access'] = 'membership_locked'
                        yield record
                    else:
                        endpoint = 'https://api.businesskoro.com/api/v1/products/slug/' + product['slug']
                        yield self.detail_record(product['id'], endpoint, lambda: parse.business_koro(self.request(endpoint).json(), data.get('deliveryCharges')))
            if page >= int(data.get('totalPages') or 1):
                break
        else:
            raise SourceError('Business Koro page limit reached.')
        if self.expected_total is None or len(seen) != self.expected_total:
            raise SourceError('Business Koro source count is missing or differs from observed identities.')

    def uddoog(self):
        seen = set()
        for page in range(1, 1001):
            catalogue = '/api/v1/dpanel/catalog' if self.tokens.get('dropshop.com.bd') else '/api/v1/storefront/products'
            data = self.request(self.origin + catalogue + '?' + urlencode({'page': page, 'limit': 100})).json()['data']
            rows = data.get('items')
            if not isinstance(rows, list):
                raise SourceError('Uddoog catalogue schema changed.')
            self.expected_total = data.get('total')
            before = len(seen)
            for product in rows:
                if product['id'] in seen:
                    continue
                seen.add(product['id'])
                if str(product['id']) in self.skip_ids:
                    continue
                endpoint = 'https://dropshop.com.bd/api/v1/storefront/products/' + product['slug']
                record = self.detail_record(product['id'], endpoint, lambda: parse.uddoog(self.request(endpoint).json()))
                # The actual verified API reference is retained until the storefront route is independently verified.
                record['url'] = 'https://dropshop.com.bd/api/v1/storefront/products/' + product['slug']
                record.setdefault('extra', {})['account_authenticated'] = bool(self.tokens.get('dropshop.com.bd'))
                yield record
            if self.expected_total is not None and len(seen) >= self.expected_total:
                break
            if not rows or len(seen) == before:
                raise SourceError('Uddoog catalogue stopped progressing before its reported total.')
        else:
            raise SourceError('Uddoog catalogue page limit reached.')

    def selfshop(self):
        vendors = self.request('https://api-v1.selfshop.com.bd/api/popular-vendors').json()['data']
        if not isinstance(vendors, list):
            raise SourceError('SelfShop original vendor directory schema changed.')
        self.coverage.update(vendor_count=len(vendors), vendor_scope='Original all-suppliers page uses popular-vendors directory')
        seen = set()
        for vendor in vendors:
            for page in range(1, 1001):
                data = self.request('https://api-v1.selfshop.com.bd/api/supplier/' + vendor['slug'] + '?' + urlencode({'page': page, 'limit': 100})).json()['data']
                products = data.get('products')
                if not isinstance(products, dict) or not isinstance(products.get('data'), list):
                    raise SourceError('SelfShop vendor-product pagination mapping requires review.')
                for p in products['data']:
                    if p['id'] in seen:
                        continue
                    seen.add(p['id'])
                    if str(p['id']) in self.skip_ids:
                        continue
                    endpoint = 'https://api-v1.selfshop.com.bd/api/product-details/' + p['ProductSlug']
                    def read_selfshop():
                        result = parse.selfshop(self.request(endpoint).json())
                        result['extra']['account_authenticated'] = bool(self.coverage.get('account_authenticated'))
                        return result
                    yield self.detail_record(p['id'], endpoint, read_selfshop, vendor_id=str(p.get('vendor_id') or ''), warehouse_id=str(p.get('warehouse_id') or ''))
                if not isinstance(products.get('current_page'), int) or not isinstance(products.get('last_page'), int):
                    raise SourceError('SelfShop pagination metadata is missing; completion cannot be confirmed.')
                if products['current_page'] == products['last_page']:
                    break
                if not products['data']:
                    raise SourceError('SelfShop vendor stopped before its last page.')
            else:
                raise SourceError('SelfShop vendor page limit reached.')
        self.coverage['distinct_product_count'] = len(seen)

    def resellkori(self):
        seen = set()
        for page in range(1, 1001):
            response = self.request('https://resellkori.com/wp-json/wc/store/v1/products?' + urlencode({'per_page': 100, 'page': page}))
            products = response.json()
            if not isinstance(products, list):
                raise SourceError('WooCommerce catalogue schema changed.')
            self.expected_total = int(response.headers['X-WP-Total']) if response.headers.get('X-WP-Total') else None
            for p in products:
                if p['id'] in seen:
                    raise SourceError('WooCommerce pagination repeated; not complete.')
                seen.add(p['id'])
                if str(p['id']) in self.skip_ids:
                    continue
                def read_detail():
                    detail = self.request(p['permalink'])
                    return parse.html_product('resellkori', detail.url, detail.content, external_id=p['id'], title=p['name'], categories=p.get('categories'))
                record = self.detail_record(p['id'], p['permalink'], read_detail)
                if record.get('_error'):
                    yield record
                    continue
                record['sku'] = p.get('sku') or ''
                record['raw_data']['store_api_product'] = p
                record['extra'].update({k: p.get(k) for k in ('average_rating', 'review_count', 'tags', 'brands', 'attributes', 'variations', 'weight', 'dimensions', 'stock_availability')})
                record['variants'] = p.get('variations') or []
                # Store API has own original-resolution image references, not related-product imagery.
                record['media'].extend(parse.media(i['src'], role='gallery', source_field='store_api.images', alt=i.get('alt')) for i in p.get('images') or [] if i.get('src'))
                yield record
            if self.expected_total is not None and len(seen) >= self.expected_total:
                break
            if not products:
                raise SourceError('WooCommerce catalogue ended without complete source totals.')
        else:
            raise SourceError('WooCommerce page limit reached.')

    def shopbase(self):
        index = html.fromstring(self.request(self.origin + '/store/products/all').content)
        scopes = [(urljoin(self.origin, a.get('href')), parse.text(a)) for a in index.xpath('//a[@href]')
                  if re.search(r'/store/products/\d+/1$', a.get('href', ''))]
        yield from self.html_scopes(scopes)

    def dropbazar(self):
        index = html.fromstring(self.request(self.origin + '/admin/store/browse').content)
        scopes = [(urljoin(self.origin, a.get('href')), parse.text(a)) for a in index.xpath('//a[@href]')
                  if re.search(r'/admin/store/products\?category=\d+', a.get('href', ''))]
        yield from self.html_scopes(scopes)

    def html_scopes(self, scopes):
        if not scopes:
            raise SourceError('Fresh source category index is empty; old catalogue is not used as a substitute.')
        seen, visited, counts = set(), set(), {}
        for first_url, category in dict(scopes).items():
            current = first_url
            while current:
                if current in visited:
                    break
                if len(visited) >= 5000:
                    raise SourceError('Source page limit reached; traversal is incomplete.')
                visited.add(current)
                doc = html.fromstring(self.request(current).content)
                pattern = r'/store/products/details/\d+$' if self.site == 'shopbase' else r'/admin/store/products/\d+$'
                links = [a for a in doc.xpath('//a[@href]') if re.search(pattern, a.get('href', ''))]
                counts[current] = len(links)
                for a in links:
                    url = urljoin(self.origin, a.get('href'))
                    ident = url.rstrip('/').split('/')[-1]
                    if ident in seen:
                        continue
                    seen.add(ident)
                    if ident in self.skip_ids:
                        continue
                    card = a
                    title = parse.text(parse.first(card, f'.//*[{parse.classes("product-name")} or {parse.classes("store-product-title")}]')) or parse.text(a)
                    if not title:
                        parent = a.getparent()
                        title = parse.text(parse.first(parent, f'.//*[{parse.classes("product-name")} or {parse.classes("store-product-title")}]'))
                    def read_detail():
                        detail = self.request(url)
                        return parse.html_product(self.site, detail.url, detail.content, external_id=ident, title=title, categories=[category])
                    yield self.detail_record(ident, url, read_detail)
                next_links = [urljoin(current, a.get('href')) for a in doc.xpath('//a[@href]')
                    if (a.get('rel') == 'next' or re.search(r'^(?:Next|পরবর্তী)', parse.text(a), re.I)) and 'disabled' not in (a.getparent().get('class') or '')]
                current = next((u for u in next_links if u not in visited), None)
        self.coverage.update(category_count=len(dict(scopes)), category_pages=len(visited), distinct_product_count=len(seen), source_page_counts=counts,
            count_limitation='Source does not provide an authoritative global product total; completed category traversal only.')

    def dropify(self):
        response = self.request(self.origin + '/products-list')
        doc = html.fromstring(response.content)
        sentinel = parse.first(doc, '//*[@id="loadMoreSentinel"]')
        if sentinel is None:
            raise SourceError('Dropify lazy-loading continuation marker is absent.')
        page, has_more, seen = 1, True, set()
        while True:
            for card in doc.xpath(f'//*[{parse.classes("product-card")}]'):
                link = parse.first(card, './/a[contains(@href,"/product/") or contains(@href,"/view-product/")]')
                if link is None and card.tag == 'a':
                    link = card
                if link is None:
                    link = parse.first(card, 'ancestor::a[contains(@href,"/product/") or contains(@href,"/view-product/")][1]')
                if link is None:
                    raise SourceError('Dropify product card has no original detail reference.')
                url = urljoin(self.origin, link.get('href'))
                ident = url.rstrip('/').split('/')[-1]
                if ident in seen:
                    continue
                seen.add(ident)
                if ident in self.skip_ids:
                    continue
                title = parse.text(parse.first(card, f'.//*[{parse.classes("product-name")}]'))
                def read_detail():
                    detail = self.request(url)
                    return parse.html_product('dropify', detail.url, detail.content, external_id=ident, title=title)
                yield self.detail_record(ident, url, read_detail)
            if page == 1:
                has_more = sentinel.get('data-has-more') == '1'
                next_page = int(sentinel.get('data-next-page') or 2)
            if not has_more:
                break
            if next_page <= page or next_page > 1000:
                raise SourceError('Dropify pagination did not progress.')
            page = next_page
            payload = self.request(self.origin + '/products-list?' + urlencode({'page': page, 'ajax': '1'}),
                headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}).json()
            doc = html.fromstring('<div>' + (payload.get('html') or '') + '</div>')
            has_more, next_page = bool(payload.get('has_more')), int(payload.get('next_page') or page + 1)
        self.coverage.update(distinct_product_count=len(seen), source_pages=page, count_basis='Original has_more/next_page lazy-loader exhausted')

    def dropshipping(self):
        if not self.coverage.get('account_authenticated'):
            raise SourceError('Authenticated reseller catalogue is required for labelled buying prices.')
        seen = set()
        for page in range(1, 1001):
            data = self.request(self.origin + '/api/reseller/show/product/list?' +
                urlencode({'page': page, 'item': 100, 'type': 'all'})).json()['products']
            if not isinstance(data.get('data'), list) or not isinstance(data.get('total'), int):
                raise SourceError('Original reseller catalogue pagination schema changed.')
            self.expected_total = data['total']
            before = len(seen)
            for product in data['data']:
                ident = str(product['id'])
                if ident in seen:
                    continue
                seen.add(ident)
                if ident in self.skip_ids:
                    continue
                url = self.origin + '/product/' + product['slug']
                def read_detail():
                    images = self.request(self.origin + '/api/product/wise/images/' + ident).json()
                    return parse.dropshipping(product, images, self.request(url).content, url)
                yield self.detail_record(ident, url, read_detail)
            if page >= data['last_page']:
                break
            if len(seen) == before:
                raise SourceError('Reseller pagination stopped progressing before its last page.')
        else:
            raise SourceError('Reseller catalogue exceeded the reviewed page bound.')
        if len(seen) != self.expected_total:
            raise SourceError('Observed reseller identities differ from the source count; completion is not claimed.')
        self.coverage.update(distinct_product_count=len(seen), source_pages=page,
                             price_basis='Source account table labels sale_price as Dropshipper Price, not Customer / Retail Price')
