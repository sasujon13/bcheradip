"""Documented, server-side READ-ONLY supplier connectors. No order submission API.

Only fixed HTTPS product endpoints are supported. Browser sessions, arbitrary
headers, redirect destinations, and public credential output are never accepted.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import quote
import requests
from django.utils import timezone
from .supplier_crypto import decrypt

LIVE = {'business_koro': 'Business Koro storefront API', 'uddoog': 'Uddoog account catalogue (read only)',
        'resellkori': 'ResellKori tracked account buying price/stock (read only)',
        'dropshipping_bd': 'Dropshipping.com.bd tracked account buying price/stock (read only)',
        'labelled_stock': 'Tracked own-page buying price / labelled stock (read only)'}
PRODUCT_URL = 'https://api.businesskoro.com/api/v1/storefront/products'
RESTRICTED = re.compile(r'\b(vape|nicotine|puffs|e[- ]?cigarette|e[- ]?liquid|ammunition|firearm|stun[- ]?gun|taser|pepper spray|self defen[cs]e (?:stick|baton)|mastercopy|master copy)\b|ই[- ]?সিগারেট|নিকোটিন', re.I)


class ConnectorError(ValueError):
    pass


def collect_uddoog_stock(supplier, continue_check=lambda: True, offer_ids=None):
    """Refresh tracked exact simple products only; never discover/import content."""
    from urllib.parse import urlencode
    from copy import deepcopy
    from .supplier_source_clients import SourceClient, SourceError
    from .supplier_source_publish import norm
    from .models import SupplierOffer
    if supplier.pk != 3:
        raise ConnectorError('This account connector is restricted to the verified Uddoog supplier identity.')
    if supplier.credential_expires_at and supplier.credential_expires_at <= timezone.now():
        raise ConnectorError('Supplier credentials have expired; reconnect before refreshing stock.')
    try:
        credentials = decrypt(supplier)
    except ValueError:
        raise ConnectorError('Supplier credentials cannot be decrypted; reconnect securely.') from None
    if not credentials.get('username') or not credentials.get('password'):
        raise ConnectorError('An encrypted supplier login is required for account buying-price checks.')
    client = SourceClient('uddoog', credentials['username'], credentials['password'])
    tracked = {}
    for offer in SupplierOffer.objects.using('ecommerce').filter(supplier=supplier, source_product__isnull=False).select_related('source_product'):
        if offer_ids is not None and offer.pk not in offer_ids:
            continue
        if offer.source_product.variants or (offer.variant_id and not re.fullmatch(r'catalogue-type-\d+',offer.variant_id)):
            continue
        tracked.setdefault(offer.external_id, []).append(offer)
    rows, seen = [], set()
    try:
        if not continue_check():
            raise ConnectorError('Update cancelled before sign-in.')
        client.login()
        for page in range(1, 1001):
            if not continue_check():
                raise ConnectorError('Update cancelled; no partial source timestamp was invented.')
            data = client.request(client.origin + '/api/v1/dpanel/catalog?' + urlencode({'page':page, 'limit':100})).json()['data']
            for product in data['items']:
                ident = str(product['id'])
                seen.add(ident)
                if ident not in tracked:
                    continue
                qty = product.get('stock')
                price = Decimal(str(product.get('base_price')))
                if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0 or not price.is_finite() or price <= 0:
                    continue
                for offer in tracked[ident]:
                    if norm(product['name']) != norm(offer.source_product.title):
                        continue  # A reused identity needs review, not a fabricated refresh.
                    rows.append({'external_id':offer.external_id,'variant_id':offer.variant_id,
                        'vendor_id':offer.vendor_id,'warehouse_id':offer.warehouse_id,
                        'title':offer.title,'url':offer.url,'identity':deepcopy(offer.identity),
                        'source_price':str(price),'currency':'BDT','quantity':qty,
                        'availability':'in_stock' if qty > 0 and product.get('status') == 'active' else 'out_of_stock',
                        'single_unit':True,'observed_at':timezone.now().isoformat()})
            if (offer_ids is not None and set(tracked).issubset(seen)) or len(seen) >= data['total']:
                break
            if not data['items']:
                raise ConnectorError('Source pagination ended early; no partial feed committed.')
        else:
            raise ConnectorError('Source pagination bound reached; update remains incomplete.')
    except (SourceError, KeyError, TypeError, ValueError, InvalidOperation):
        raise ConnectorError('Supplier stock/price refresh failed. Cached timestamps and stock were not fabricated.') from None
    finally:
        client.close()
        credentials.clear()
    return rows, {'tracked_source_products':len(tracked),'returned_rows':len(rows),
                  'content_downloads':0,'imports':0,'supplier_orders':0}


def collect_resellkori_stock(supplier, continue_check=lambda: True, offer_ids=None):
    """Revisit saved simple-product URLs, extract only current reseller cost/stock.

    No catalogue discovery, descriptions, images or local content are updated.
    The supplier has no verified bulk buying-price endpoint; this is slower.
    """
    from copy import deepcopy
    from lxml import html
    from .supplier_source_clients import SourceClient, SourceError
    from .supplier_source_parsers import html_product
    from .supplier_source_publish import norm
    from .models import SupplierOffer
    if supplier.pk != 8:
        raise ConnectorError('Tracked account connector is restricted to verified ResellKori identity.')
    if supplier.credential_expires_at and supplier.credential_expires_at <= timezone.now():
        raise ConnectorError('Supplier credentials expired; reconnect before refreshing.')
    try:
        credentials=decrypt(supplier)
    except ValueError:
        raise ConnectorError('Supplier credentials cannot be decrypted; reconnect securely.') from None
    if not credentials.get('username') or not credentials.get('password'):
        raise ConnectorError('An encrypted account login is required for reseller buying prices.')
    client=SourceClient('resellkori',credentials['username'],credentials['password'])
    rows=[]
    try:
        if not continue_check():
            raise ConnectorError('Update cancelled before sign-in.')
        client.login()
        offers=SupplierOffer.objects.using('ecommerce').filter(supplier=supplier,
            source_product__isnull=False,imported_product__isnull=False).select_related('source_product')
        if offer_ids is not None:
            offers = offers.filter(pk__in=offer_ids)
        for offer in offers.iterator():
            if not continue_check():
                raise ConnectorError('Update cancelled; no partial source timestamps fabricated.')
            source=offer.source_product
            if source.variants or source.raw_data.get('store_api_product',{}).get('type') != 'simple':
                continue
            response=client.request(source.url)
            doc=html.fromstring(response.content)
            # This theme omits the usual WooCommerce cart form. Its own main
            # product container carries the stable ID; related-card IDs do not.
            if not doc.xpath('//*[@id=$own]', own='product-'+str(source.external_id)):
                continue
            data=html_product('resellkori',response.url,response.content,external_id=source.external_id)
            if norm(data['title']) != norm(source.title):
                continue
            quantity=data['stock'].get('quantity')
            own=doc.xpath('//*[@id=$own]', own='product-'+str(source.external_id))[0]
            if 'outofstock' in own.get('class','').split():
                quantity=0
            cost=Decimal(data['prices'].get('reseller',{}).get('amount') or '0')
            confirmation=quantity is None and 'instock' in own.get('class','').split()
            if (not confirmation and (isinstance(quantity,bool) or not isinstance(quantity,int) or quantity < 0)) or not cost.is_finite() or cost <= 0:
                continue
            rows.append({'external_id':offer.external_id,'variant_id':offer.variant_id,
                'vendor_id':offer.vendor_id,'warehouse_id':offer.warehouse_id,'title':offer.title,
                'url':offer.url,'identity':deepcopy(offer.identity),'source_price':str(cost),'currency':'BDT',
                'quantity':quantity,'availability':'in_stock' if quantity or confirmation else 'out_of_stock',
                'single_unit':True,'observed_at':timezone.now().isoformat()})
    except (SourceError,KeyError,TypeError,ValueError,InvalidOperation):
        raise ConnectorError('Supplier refresh failed. No stock or timestamps fabricated; retry through normal access.') from None
    finally:
        client.close();credentials.clear()
    return rows,{'tracked_source_products':len(rows),'returned_rows':len(rows),'content_writes':0,'imports':0,'supplier_orders':0}


def collect_dropshipping_stock(supplier, continue_check=lambda: True, offer_ids=None):
    """Read labelled reseller costs and own-page exact stock for tracked IDs only."""
    from copy import deepcopy
    from urllib.parse import urlencode
    from lxml import html
    from .models import SupplierOffer
    from .supplier_source_clients import SourceClient, SourceError
    from .supplier_source_publish import norm
    if supplier.pk != 9:
        raise ConnectorError('This connector is restricted to the inspected Dropshipping.com.bd identity.')
    if supplier.credential_expires_at and supplier.credential_expires_at <= timezone.now():
        raise ConnectorError('Supplier credentials expired; reconnect securely.')
    try:
        credentials=decrypt(supplier)
    except ValueError:
        raise ConnectorError('Supplier credentials cannot be decrypted; reconnect securely.') from None
    if not credentials.get('username') or not credentials.get('password'):
        raise ConnectorError('Encrypted account login is required for labelled dropshipper prices.')
    client=SourceClient('dropshipping',credentials['username'],credentials['password'])
    tracked={o.source_product.external_id:o for o in SupplierOffer.objects.using('ecommerce').filter(
        supplier=supplier,source_product__isnull=False,imported_product__isnull=False).select_related('source_product')
        if (offer_ids is None or o.pk in offer_ids) and (not o.variant_id or re.fullmatch(r'catalogue-type-\d+',o.variant_id)) and not o.source_product.variants}
    rows=[];seen=set()
    try:
        if not continue_check(): raise ConnectorError('Update cancelled before sign-in.')
        client.login()
        for page in range(1,1001):
            if not continue_check(): raise ConnectorError('Update cancelled before source request.')
            data=client.request(client.origin+'/api/reseller/show/product/list?'+urlencode(
                {'page':page,'item':100,'type':'all'})).json()['products']
            before=len(seen)
            for product in data['data']:
                ident=str(product['id'])
                if ident in seen: continue
                seen.add(ident); offer=tracked.get(ident)
                if not offer or norm(product['name']) != norm(offer.source_product.title): continue
                if not continue_check(): raise ConnectorError('Update cancelled; no partial feed committed.')
                doc=html.fromstring(client.request(offer.source_product.url).content)
                ids=doc.xpath('//*[@id="single_page_product_id"]/@value')
                qty=doc.xpath('//*[@id="product_stock"]/@value')
                if ids != [ident] or len(qty)!=1 or not re.fullmatch(r'-?\d+',qty[0]): continue
                quantity=max(0,int(qty[0])); price=Decimal(str(product.get('sale_price')))
                if not price.is_finite() or price<=0 or quantity>100000000: continue
                rows.append({'external_id':offer.external_id,'variant_id':offer.variant_id,'vendor_id':offer.vendor_id,
                    'warehouse_id':offer.warehouse_id,'title':offer.title,'url':offer.url,'identity':deepcopy(offer.identity),
                    'source_price':str(price),'currency':'BDT','quantity':quantity,
                    'availability':'in_stock' if quantity>0 and product.get('status')==1 else 'out_of_stock',
                    'single_unit':True,'observed_at':timezone.now().isoformat()})
            if (offer_ids is not None and set(tracked).issubset(seen)) or page>=data['last_page']: break
            if len(seen)==before: raise ConnectorError('Source pagination stopped early.')
        else: raise ConnectorError('Source page bound reached.')
        if offer_ids is None and len(seen)!=data['total']: raise ConnectorError('Source count mismatch; partial feed not committed.')
    except (SourceError,KeyError,TypeError,ValueError,InvalidOperation):
        raise ConnectorError('Supplier price/stock refresh failed; no stock or check timestamps fabricated.') from None
    finally:
        client.close();credentials.clear()
    return rows,{'tracked_source_products':len(tracked),'returned_rows':len(rows),'content_writes':0,'imports':0,'supplier_orders':0}


def collect_labelled_stock(supplier, continue_check=lambda: True, offer_ids=None):
    from copy import deepcopy
    from .supplier_label_stock import SITES, read_stock, remember_stock, missing_stock
    from .supplier_source_clients import SourceClient, SourceError
    from .models import SupplierOffer
    if supplier.pk not in SITES or not supplier.enabled or not supplier.terms_confirmed:
        raise ConnectorError('Labelled-stock access requires an enabled inspected supplier.')
    if supplier.credential_expires_at and supplier.credential_expires_at<=timezone.now():
        raise ConnectorError('Supplier credentials expired; reconnect first.')
    try:
        credentials=decrypt(supplier)
    except ValueError:
        raise ConnectorError('Encrypted account credentials are unavailable; reconnect securely.') from None
    client=SourceClient(SITES[supplier.pk],credentials.get('username',''),credentials.get('password',''))
    rows=[]
    try:
        if not continue_check():raise ConnectorError('Cancelled before sign-in.')
        client.login()
        offers=SupplierOffer.objects.using('ecommerce').filter(supplier=supplier,
            source_product__isnull=False,imported_product__isnull=False).select_related('source_product','imported_product')
        if offer_ids is not None:
            offers = offers.filter(pk__in=offer_ids)
        for offer in offers.iterator():
            if not continue_check():raise ConnectorError('Cancelled; remaining checks were not performed.')
            source=offer.source_product
            try:
                data=read_stock(client,source)
            except SourceError as exc:
                if 'HTTP 404;' not in str(exc):raise
                data=missing_stock(source)
            checked=remember_stock(source,data)
            field='wholesale' if supplier.pk==7 else 'reseller_price'
            status=data['stock'].get('status')
            minimum=Decimal(data['prices'].get('minimum_selling_price',{}).get('amount') or '0')
            below_minimum=minimum>0 and offer.imported_product.variants.filter(price__lt=minimum).exists()
            rows.append({'external_id':offer.external_id,'variant_id':offer.variant_id,
                'vendor_id':offer.vendor_id,'warehouse_id':offer.warehouse_id,'title':offer.title,
                'url':offer.url,'identity':deepcopy(offer.identity),'currency':'BDT',
                'source_price':data['prices'][field]['amount'],'quantity':data['stock'].get('quantity'),
                'availability':'in_stock' if status=='in_stock' and not below_minimum else 'out_of_stock' if status=='out_of_stock' else 'unconfirmed',
                'single_unit':True,'observed_at':checked.isoformat()})
    except (SourceError,KeyError,TypeError,ValueError,InvalidOperation):
        raise ConnectorError('Own-page stock/price refresh incomplete. No quantities or successful timestamps fabricated; retry normal access.') from None
    finally:
        client.close();credentials.clear()
    return rows,{'returned_rows':len(rows),'content_writes':0,'imports':0,'supplier_orders':0}


def collect(supplier, continue_check=lambda: True, offer_ids=None):
    if supplier.connector == 'labelled_stock':
        return collect_labelled_stock(supplier, continue_check, offer_ids)
    if supplier.connector == 'uddoog':
        return collect_uddoog_stock(supplier, continue_check, offer_ids)
    if supplier.connector == 'resellkori':
        return collect_resellkori_stock(supplier, continue_check, offer_ids)
    if supplier.connector == 'dropshipping_bd':
        return collect_dropshipping_stock(supplier, continue_check, offer_ids)
    if supplier.connector != 'business_koro':
        raise ConnectorError('No verified read-only API connector is available for this supplier.')
    expires = getattr(supplier, 'credential_expires_at', None)
    if expires and expires <= timezone.now():
        raise ConnectorError('Supplier API credentials have expired. Replace them before requesting source data.')
    if not continue_check():
        raise ConnectorError('Collection stopped before requesting the supplier.')
    try:
        credentials = decrypt(supplier)
    except ValueError:
        raise ConnectorError('Supplier credentials cannot be read. Check server encryption and replace credentials securely.') from None
    key = credentials.get('api_key', '').strip()
    domain = credentials.get('domain', '').strip()
    if not key or len(key) > 4096 or any(x in key for x in '\r\n'):
        raise ConnectorError('A valid supplier API key is required.')
    if domain and (len(domain) > 253 or not re.fullmatch(r'[A-Za-z0-9.-]+', domain)):
        raise ConnectorError('Use a hostname only for the registered integration domain.')
    headers = {'x-api-key': key, 'Accept': 'application/json'}
    if domain:
        headers['x-domain'] = domain
    session = requests.Session()
    session.trust_env = False  # Do not forward credentials through environment proxies.
    try:
        response = session.get(PRODUCT_URL, headers=headers, timeout=(10, 40), allow_redirects=False, stream=True)
        if response.status_code in (401, 403):
            raise ConnectorError('Supplier denied API access. Verify the key, domain, membership and supplier approval.')
        if response.status_code == 429:
            raise ConnectorError('Supplier API quota reached. Retry later; no stock timestamp was refreshed.')
        if response.status_code != 200:
            raise ConnectorError(f'Supplier product API returned HTTP {response.status_code}. No source data was changed.')
        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            if not continue_check():
                raise ConnectorError('Collection stopped while reading the supplier response.')
            body.extend(chunk)
            if len(body) > 10 * 1024 * 1024:
                raise ConnectorError('Supplier response exceeds the safe limit; request a documented paginated feed.')
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise ConnectorError('Supplier returned an invalid JSON response. No source data was changed.') from None
    except requests.RequestException:
        # Never echo the request, headers, credentials or supplier error response.
        raise ConnectorError('Supplier product API could not be reached securely. No source data was changed.') from None
    finally:
        session.close()
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise ConnectorError('Supplier product response does not match the documented data list.')
    if payload.get('next') or payload.get('next_page_url') or (isinstance(payload.get('links'), dict) and payload['links'].get('next')):
        raise ConnectorError('Supplier indicates additional pages. A documented pagination mapping is required before marking collection complete.')
    now = timezone.now().isoformat()
    rows, stats = [], {'source_products': len(payload['data']), 'restricted_skipped': 0, 'invalid_skipped': 0}
    for product in payload['data']:
        if not isinstance(product, dict):
            stats['invalid_skipped'] += 1
            continue
        title = str(product.get('name') or '').strip()
        if RESTRICTED.search(title):
            stats['restricted_skipped'] += 1
            continue
        try:
            source_price = Decimal(str(product['costPrice']))
            if not source_price.is_finite() or source_price < 0 or source_price >= Decimal('1000000000000'):
                raise ValueError()
            product_id = str(product['id']).strip()
            if not title or not product_id or len(product_id) > 120:
                raise ValueError()
        except (KeyError, ValueError, InvalidOperation):
            stats['invalid_skipped'] += 1
            continue
        variants = product.get('variants') or [{}]
        if not isinstance(variants, list) or any(not isinstance(v, dict) for v in variants):
            stats['invalid_skipped'] += 1
            continue
        for variant in variants:
            # Colour/size are documented; do not pretend a derived key is a supplier-issued SKU.
            spec = {k: str(variant[k])[:100] for k in ('color', 'size') if variant.get(k) is not None}
            variant_id = 'spec-' + hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:32] if spec else ''
            identity = {'authenticity': 'unverified', 'tax_basis': 'unconfirmed'}
            if isinstance(product.get('category'), str) and product['category'].strip():
                identity['category'] = product['category'].strip()[:160]
            if spec:
                identity['variant'] = ' / '.join(spec.values())[:200]
                identity['specifications'] = spec
            for field in ('brand', 'model', 'sku'):
                if isinstance(product.get(field), str) and product[field].strip():
                    identity[field] = product[field].strip()[:120]
            available = variant.get('inStock', product.get('inStock'))
            quantity = variant.get('stockQuantity', product.get('stockQuantity') if len(variants) == 1 else None)
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 <= quantity <= 100000000:
                quantity = None
            rows.append({'external_id': product_id, 'variant_id': variant_id, 'vendor_id': 'not-provided',
                'warehouse_id': '', 'title': title[:255],
                'url': 'https://www.businesskoro.com/dashboard/products#' + quote(product_id, safe=''),
                'identity': identity, 'source_price': str(source_price.quantize(Decimal('.01'))), 'currency': 'BDT',
                'availability': 'in_stock' if available is True else 'out_of_stock' if available is False else 'unconfirmed',
                'quantity': quantity, 'weight_grams': None, 'single_unit': False, 'observed_at': now})
            if len(rows) > 20000:
                raise ConnectorError('Source variant count exceeds one safe batch. Configure documented pagination before continuing.')
    if stats['invalid_skipped'] and not rows and payload['data']:
        raise ConnectorError('No products matched the documented source-price/identity schema. Review the supplier response mapping.')
    return rows, stats
