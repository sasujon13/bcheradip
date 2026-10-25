"""Publish only freshly observed, orderable source variants. No supplier purchases.

The first verified price/variant adapter is Business Koro. Other rich catalogues
remain private until their account-specific buying/stock semantics are checked.
"""
from collections import Counter
from datetime import timedelta
from decimal import Decimal
import hashlib
import io
import json
import logging
from urllib.parse import urlsplit

import requests
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.html import strip_tags
from html import unescape

from .models import (SupplierSourceProduct, SupplierSourceMedia, SupplierOffer, Product,
                     ProductVariant, ProductImage, OrderItem,DeliverySettings)
from .supplier_recollection import reference_url
from .supplier_connectors import RESTRICTED
from .supplier_service import audit, costs_for
from .manual_catalogue import import_offer, purchasable_offers
from .pricing import calculate_price, retail_prices
from .supplier_confirmation import MARKER as CONFIRMATION_MARKER

DB = 'ecommerce'
IMAGE_HOSTS = {2: {'cdn.businesskoro.com'}, 3: {'dropshop.com.bd'},
               8: {'resellkori.com', 'www.resellkori.com'},
               9: {'dropshipping.com.bd', 'www.dropshipping.com.bd'}}
IMAGE_HOSTS.update({1:{'shopbasebd.com'},6:{'dropbazarbd.com'},7:{'www.dropifybd.com','dropifybd.com'}})


def verify_photo(media):
    """Cache original bytes from an inspected fixed supplier CDN, never a proxy URL."""
    reference_url(media.original_url)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)
    if urlsplit(media.original_url).hostname not in IMAGE_HOSTS.get(media.product.supplier_id, set()):
        raise ValueError('This supplier image host still requires a reviewed download adapter.')
    name = (media.metadata or {}).get('cached_name')
    if (name and name.startswith('supplier_products/') and media.metadata.get('verified_image') and
            media.metadata.get('verified_run_id')==str(media.last_run_id) and default_storage.exists(name)):
        return media
    with requests.Session() as session:
        session.trust_env = False
        try:
            with session.get(media.original_url, timeout=(10, 30), allow_redirects=False, stream=True) as response:
                if response.status_code != 200 or not response.headers.get('Content-Type', '').lower().startswith('image/'):
                    raise ValueError('Original supplier photo is not currently accessible.')
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > 15 * 1024 * 1024:
                        raise ValueError('Original image exceeds the reviewed size limit.')
        except requests.RequestException:
            raise ValueError('Original supplier photo could not be downloaded securely.') from None
    with Image.open(io.BytesIO(body)) as image:
        image.verify()
        image_format, width, height = image.format, image.width, image.height
    extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif', 'AVIF': 'avif'}.get(image_format)
    if not extension or min(width, height) < 32:
        raise ValueError('Supplier image is not a supported product photo.')
    name = 'supplier_products/' + hashlib.sha256(body).hexdigest() + '.' + extension
    if not default_storage.exists(name):
        name = default_storage.save(name, ContentFile(bytes(body)))
    media.stored_url = '/manage' + settings.MEDIA_URL + name
    media.metadata = {**media.metadata, 'verified_image': True, 'cached_name': name,
                      'verified_run_id':str(media.last_run_id),'verified_at':timezone.now().isoformat(),
                      'sha256': hashlib.sha256(body).hexdigest(), 'width': width, 'height': height}
    media.metadata.pop('verification_error', None)
    media.save(using=DB, update_fields=['stored_url', 'metadata', 'updated_at'])
    return media


def norm(value):
    return ' '.join(str(value or '').casefold().split())


def stock_observed_at(source):
    from django.utils.dateparse import parse_datetime
    value=source.extra.get('price_stock_checked_at') if source.supplier_id in (1,6,7) else None
    checked=parse_datetime(value) if isinstance(value,str) else None
    return checked if checked and timezone.is_aware(checked) else source.observed_at


def source_variants(source):
    if source.supplier_id in (1,6,7):
        if source.variants or source.extra.get('variant_inputs'):
            raise ValueError('Source options need exact variant mapping before release; quantity confirmation does not select an unknown option.')
        if source.stock.get('status') != 'in_stock':
            raise ValueError('Supplier has not explicitly confirmed this product in stock.')
        field='wholesale' if source.supplier_id==7 else 'reseller_price'
        cost=Decimal(source.prices.get(field,{}).get('amount') or '0')
        if not cost.is_finite() or cost<=0:
            raise ValueError('A confirmed source buying price is required, not a suggested retail price.')
        if source.supplier_id==7 and not source.extra.get('account_price_verified'):
            raise ValueError('Signed-in wholesale-price evidence is required.')
        quantity=source.stock.get('quantity')
        if quantity is not None and (isinstance(quantity,bool) or not isinstance(quantity,int) or not 0<=quantity<=100000000):
            raise ValueError('Invalid source quantity; no invented stock count.')
        return [{'id':'','legacy_id':'','spec':{},'quantity':quantity,'cost':cost,'confirmation_required':quantity is None}]
    if source.supplier_id in (3, 8, 9):
        if source.variants:
            raise ValueError('Separate options are present but exact variant quantities/prices still need verification.')
        if source.supplier_id == 3:
            if not source.extra.get('account_authenticated') or source.stock.get('status') != 'active':
                raise ValueError('Active account-authenticated supplier catalogue observation is required.')
            cost = source.prices.get('base_price', {}).get('amount')
        elif source.supplier_id == 8:
            raw = source.raw_data.get('store_api_product') or {}
            if raw.get('type') != 'simple' or raw.get('is_in_stock') is not True:
                raise ValueError('Only simple, in-stock products with verified reseller cost are supported here.')
            cost = source.prices.get('reseller', {}).get('amount')
        else:
            if (not source.extra.get('account_authenticated') or source.stock.get('status') != 'in_stock' or
                    source.stock.get('status_code') != 1):
                raise ValueError('An active account-labelled dropshipper price and exact positive stock are required.')
            cost = source.prices.get('sale_price', {}).get('amount')
        quantity = source.stock.get('quantity')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 <= quantity <= 100000000:
            raise ValueError('A confirmed numeric quantity is required; stock labels are not invented quantities.')
        cost = Decimal(cost or '0')
        if not cost.is_finite() or cost <= 0:
            raise ValueError('Confirmed account buying price is missing.')
        return [{'id': '', 'legacy_id': '', 'spec': {}, 'quantity': quantity, 'cost': cost}]
    if source.supplier_id != 2:
        raise ValueError('Buying price and exact variant stock are not yet verified for this supplier adapter.')
    raw = source.raw_data.get('product') or {}
    if raw.get('locked') or source.extra.get('content_access') == 'membership_locked':
        raise ValueError('Supplier membership does not permit this product.')
    if str(raw.get('status', '')).upper() != 'ACTIVE':
        raise ValueError('Supplier product is not active.')
    cost = Decimal(source.prices.get('baseCost', {}).get('amount') or '0')
    if not cost.is_finite() or cost <= 0:
        raise ValueError('Confirmed account buying price is missing.')
    rows = source.variants or [{'id': '', 'stockQuantity': source.stock.get('quantity')}]
    result = []
    for row in rows:
        quantity = row.get('stockQuantity')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 <= quantity <= 100000000:
            continue
        spec = {key: str((row.get(key) or {}).get('name') or '') for key in ('color', 'size')}
        spec = {key: value for key, value in spec.items() if value}
        # Old storefront rows use this documented colour/size-derived key. Keep
        # it, while recording the supplier's actual variant UUID separately.
        legacy_id = 'spec-' + hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:32] if spec else ''
        result.append({'id': str(row.get('id') or ''), 'legacy_id': legacy_id,
                       'spec': spec, 'quantity': quantity, 'cost': cost})
    if not result:
        raise ValueError('No exact variant quantity is supplied; aggregate stock is not substituted.')
    return result


def trusted_stock_identity(offer, row):
    """Saved enriched descriptions/specs need not equal the API's lightweight card.

    Nevertheless, require the original parent, exact colour/size-derived key,
    current original title and every source option before accepting a refresh.
    """
    if not offer.source_product_id:
        return False
    source = offer.source_product
    if offer.supplier_id in (1,6,7,9):
        # Legacy cards used the public URL suffix, not the internal API ID.
        # The account connector checks that API ID against the source's own
        # page, then returns the saved offer identity without changing history.
        return bool(not source.variants and not offer.variant_id and row['external_id']==offer.external_id and
                    row['url']==source.url and row['identity']==offer.identity and norm(row['title'])==norm(offer.title))
    if offer.supplier_id in (3, 8):
        return bool(not source.variants and not offer.variant_id and
                    row['external_id'] == source.external_id and row['identity'] == offer.identity and
                    norm(row['title']) == norm(offer.title))
    if offer.supplier_id != 2:
        return False
    if row['external_id'] != source.external_id or norm(row['title']) != norm(source.title):
        return False
    try:
        variants = source_variants(source)
    except ValueError:
        return False
    incoming = (row.get('identity') or {}).get('specifications') or {}
    return any(row['variant_id'] == v['legacy_id'] and
               all(norm(incoming.get(k)) == norm(value) for k, value in v['spec'].items())
               for v in variants)


def refresh_listing_stock(offer):
    """Update only exact saved variant availability/cost, never accepted order prices."""
    if not offer.imported_product_id:
        return
    product = Product.objects.using(DB).select_for_update().get(pk=offer.imported_product_id)
    variants = list(product.variants.select_for_update())
    if len(variants) != 1 or not product.attributes.get('manual_supplier_catalogue'):
        return
    variant = variants[0]
    reserved = OrderItem.objects.using(DB).filter(variant_id=variant.pk,
        order__status__in=('pending', 'confirmed', 'processing')).aggregate(n=Sum('quantity'))['n'] or 0
    stock_known = offer.availability == 'in_stock' and offer.quantity is not None and offer.quantity > 0
    confirmation = offer.availability == 'in_stock' and offer.quantity is None and offer.supplier_id in (1,6,7)
    variant.stock = max(0, offer.quantity-reserved) if stock_known else 0
    variant.cost_price, variant.allow_backorder = offer.source_price, confirmation
    variant.save(using=DB, update_fields=['stock', 'cost_price', 'allow_backorder', 'updated_at'])
    costs = costs_for(offer)
    source_cost = Decimal(str(offer.source_price or '0'))
    floor = source_cost + sum((costs[k] for k in
        ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs', 'fees', 'taxes')), Decimal('0'))
    minimum = Decimal(offer.source_product.prices.get('minimum_selling_price',{}).get('amount') or '0') if offer.supplier_id==7 else Decimal('0')
    ready = bool(source_cost > 0 and variant.price > floor and variant.price >= minimum)
    was_source_hold = bool(product.attributes.get('source_stock_hold'))
    attributes = {**product.attributes, 'supplier_publication_ready': ready, CONFIRMATION_MARKER:confirmation}
    Product.objects.using(DB).filter(pk=product.pk).update(attributes=attributes)
    orderable = purchasable_offers().filter(pk=offer.pk).exists()
    if not orderable and (product.status == 'active' or was_source_hold):
        attributes['source_stock_hold'] = True
        Product.objects.using(DB).filter(pk=product.pk).update(status='archived', attributes=attributes)
    elif orderable and was_source_hold:
        attributes['source_stock_hold'] = False
        Product.objects.using(DB).filter(pk=product.pk).update(status='active', attributes=attributes)
    # A staff archive without this source-hold marker is never restored.
    audit('verified_listing_stock_refreshed', supplier=offer.supplier, offer=offer,
          available_after_local_reservations=variant.stock, selling_price_preserved=True,
          photos_unchanged=True, source_checked_at=offer.observed_at.isoformat())


@transaction.atomic(using=DB)
def apply_variant(source_id, row, media_ids):
    source = SupplierSourceProduct.objects.using(DB).select_for_update().select_related('supplier').get(pk=source_id)
    images = list(SupplierSourceMedia.objects.using(DB).filter(pk__in=media_ids, last_run_id=source.last_run_id,
                                                             metadata__verified_image=True).order_by('position', 'pk'))
    if not images or source.quality.get('missing'):
        raise ValueError('Complete original content and verified original photos are required.')
    if (not source.supplier.enabled or not source.supplier.terms_confirmed or
            not timezone.now()-timedelta(hours=24) <= stock_observed_at(source) <= timezone.now()):
        raise ValueError('Current authorised source observation is required.')
    parent = SupplierOffer.objects.using(DB).select_for_update().filter(supplier_id=source.supplier_id).filter(
        Q(external_id=source.external_id) | Q(url=source.url))
    if parent.filter(state='excluded').exists() or parent.exclude(excluded_reason='').exists() or RESTRICTED.search(source.title):
        raise ValueError('Manual or restricted-product exclusion is preserved.')
    candidates = list(parent)
    exact = [o for o in candidates if o.variant_id in (row['id'], row['legacy_id'])]
    if not exact:
        exact = [o for o in candidates if row['spec'] and all(
            norm((o.identity.get('specifications') or {}).get(k)) == norm(v) for k, v in row['spec'].items())]
    if len(exact) > 1:
        raise ValueError('More than one historical offer matches this exact source variant; review required.')
    if exact:
        offer, created = exact[0], False
    else:
        offer, created = SupplierOffer.objects.using(DB).get_or_create(supplier_id=source.supplier_id,
            external_id=source.external_id, variant_id=row['legacy_id'], vendor_id='not-provided', warehouse_id='',
            defaults={'title': source.title[:255], 'url': source.url})
    # Do not mutate matching identity/evidence. Provider IDs live in the separate source table.
    newer_stock = bool(not created and offer.source_product_id == source.pk and
                       offer.observed_at and offer.observed_at > stock_observed_at(source))
    if newer_stock:
        # A source-content release must not undo a more recent stock-only API
        # check (including an out-of-stock result) or move its timestamp back.
        if offer.source_price is None or offer.source_price <= 0 or offer.currency != 'BDT':
            raise ValueError('Newer supplier price is unconfirmed; older content cannot replace it.')
        quantity = offer.quantity if offer.availability == 'in_stock' else 0
        confirmation = bool(quantity is None and offer.availability=='in_stock' and source.supplier_id in (1,6,7))
        if not confirmation and (isinstance(quantity,bool) or not isinstance(quantity,int) or quantity < 0):
            raise ValueError('Newer supplier quantity is unconfirmed; older content cannot replace it.')
        row = {**row, 'cost': offer.source_price, 'quantity': quantity, 'confirmation_required':confirmation}
    else:
        offer.source_price, offer.currency = row['cost'], 'BDT'
        offer.quantity, offer.availability = row['quantity'], 'in_stock' if row['quantity'] or row.get('confirmation_required') else 'out_of_stock'
        offer.observed_at = stock_observed_at(source)
    offer.source_product, offer.single_unit, offer.url = source, True, source.url
    offer.preview_images = list(dict.fromkeys(m.original_url for m in images))
    packaging = source.prices.get('packagingCost', {}).get('amount')
    if packaging is not None:
        offer.costs = {**offer.costs, 'packaging_cost': packaging}
    if created:
        offer.identity = {'variant': ' / '.join(row['spec'].values()) or 'Default',
                          'specifications': row['spec'], 'authenticity': 'unverified', 'tax_basis': 'unconfirmed'}
        if source.categories and isinstance(source.categories[0], dict):
            offer.identity['category'] = source.categories[0].get('name') or 'Supplier collection'
    offer.save(using=DB)
    new_listing = not offer.imported_product_id
    if new_listing:
        import_offer(offer.pk)
        offer.refresh_from_db(using=DB)
    product = Product.objects.using(DB).select_for_update().get(pk=offer.imported_product_id)
    variants = list(product.variants.select_for_update())
    if len(variants) > 1:
        raise ValueError('Historical listing contains multiple variants for one offer; no stock overwritten.')
    costs = costs_for(offer)
    suggestion = calculate_price(row['cost'], {k: str(costs[k]) for k in
        ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs')}, subsidy_enabled=False,
        rules=DeliverySettings.current().pricing_rules)['suggested_price']
    minimum = Decimal(source.prices.get('minimum_selling_price',{}).get('amount') or '0') if source.supplier_id==7 else Decimal('0')
    if minimum.is_finite() and minimum>0:
        suggestion = str(max(Decimal(suggestion),minimum))
    if variants:
        variant = variants[0]
        # Staff/manual selling prices and accepted order items are never overwritten.
        if not variant.is_active:
            raise ValueError('Staff-disabled variant remains disabled.')
    else:
        variant = ProductVariant(product=product, sku=f'CATALOGUE-{offer.pk}', price=Decimal(suggestion))
    # Reserve the owner-requested future discount on NEW listings, once only.
    # Existing staff prices need the explicit, audited repricing operation.
    retail_rule = None
    if new_listing or not product.attributes.get('_retail_pricing', {}).get(str(variant.pk)):
        # The owner explicitly requested the reserve/rounding on existing
        # imported drafts too. Record their current baseline once, instead of
        # leaving old fractional prices live or compounding on future refresh.
        baseline=Decimal(suggestion if new_listing else variant.price)
        if product.status in ('draft','archived'):
            baseline=max(baseline,minimum)
        retail_rule = retail_prices(baseline,DeliverySettings.current().pricing_rules)
        mode = getattr(settings, 'COMMERCE_SUPPLIER_RETAIL_MODE', 'sale')
        variant.price = Decimal(retail_rule['regular_price'] if mode == 'reserve' else retail_rule['sale_price'])
        variant.compare_at_price = Decimal(retail_rule['regular_price']) if mode == 'sale' else None
        retail_rule.update(mode=mode, applied_price=str(variant.price), updated_at=timezone.now().isoformat())
    elif minimum>variant.price and product.status in ('draft','archived'):
        previous=product.attributes.get('_retail_pricing',{}).get(str(variant.pk),{})
        if previous.get('applied_price') is not None and variant.price==Decimal(previous['applied_price']):
            # Correct an unchanged generated draft, never a staff-edited price.
            retail_rule=retail_prices(minimum,DeliverySettings.current().pricing_rules)
            mode=getattr(settings,'COMMERCE_SUPPLIER_RETAIL_MODE','sale')
            variant.price=Decimal(retail_rule['regular_price'] if mode=='reserve' else retail_rule['sale_price'])
            variant.compare_at_price=Decimal(retail_rule['regular_price']) if mode=='sale' else None
            retail_rule.update(mode=mode,applied_price=str(variant.price),updated_at=timezone.now().isoformat(),
                               minimum_source_selling_price=str(minimum))
    variant.cost_price, variant.currency, variant.allow_backorder = row['cost'], 'BDT', bool(row.get('confirmation_required'))
    reserved = 0
    if variant.pk:
        reserved = OrderItem.objects.using(DB).filter(variant_id=variant.pk,
            order__status__in=('pending', 'confirmed', 'processing')).aggregate(n=Sum('quantity'))['n'] or 0
    variant.stock = 0 if row.get('confirmation_required') else max(0, row['quantity']-reserved)
    if created or not variant.title or variant.title == 'Default':
        variant.title = ' / '.join(row['spec'].values()) or 'Default'
    for n, (key, value) in enumerate(row['spec'].items(), 1):
        setattr(variant, f'option{n}_name', key.title())
        setattr(variant, f'option{n}_value', value)
    variant.save(using=DB)
    floor = row['cost'] + sum((costs[k] for k in ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs', 'fees', 'taxes')), Decimal('0'))
    updates = {'attributes': {**product.attributes, 'manual_supplier_catalogue': True,
        CONFIRMATION_MARKER: bool(row.get('confirmation_required')),
        'supplier_publication_ready': variant.price > floor and variant.price >= minimum}}
    from .catalog_structure import classify, ensure_category
    from .product_content import option_review
    category_plan = classify(source.title, source.categories, source.description)
    previous_catalog = product.attributes.get('_catalog', {})
    if previous_catalog.get('manual_category'):
        category_plan = {**previous_catalog, 'status': 'assigned'}
    elif category_plan['path']:
        updates['category'] = ensure_category(tuple(category_plan['path']))
    updates['attributes']['_catalog'] = {**category_plan, 'variant_review': option_review(source, [variant])}
    if retail_rule:
        updates['attributes']['_retail_pricing'] = {
            **product.attributes.get('_retail_pricing', {}), str(variant.pk): retail_rule}
    from .supplier_recollection import preferred_description,description_text
    if not description_text(product.description):
        updates['description'] = preferred_description(source)
    Product.objects.using(DB).filter(pk=product.pk).update(**updates)
    for n, image in enumerate(images):
        listing_image, _ = ProductImage.objects.using(DB).get_or_create(product=product, url=image.stored_url,
            defaults={'source_media': image, 'position': n, 'alt_text': product.name})
        ProductImage.objects.using(DB).filter(pk=listing_image.pk).update(source_media=image, position=n)
    # Never delete historical/manual photos. Public serializers select current,
    # provenanced source media only, so old wrong images cannot be the thumbnail.
    orderable = category_plan['status'] == 'assigned' and variant.price > floor and purchasable_offers().filter(pk=offer.pk).exists()
    Product.objects.using(DB).filter(pk=product.pk).update(status='active' if orderable else 'archived')
    audit('fresh_supplier_variant_applied', supplier=source.supplier, offer=offer, source_product_id=source.pk,
          source_variant_id=row['id'], source_run=str(source.last_run_id), quantity=row['quantity'],
          available_after_local_reservations=variant.stock, photos=len(images), published=orderable,
          selling_price_preserved=bool(variants), automatic_supplier_purchasing=False)
    return 'published' if orderable else 'held'


def publish_source(source_id):
    source = SupplierSourceProduct.objects.using(DB).get(pk=source_id)
    if not source.supplier.enabled or not source.supplier.terms_confirmed:
        raise ValueError('Supplier access is paused or not approved; no image requests or publication attempted.')
    if source.quality.get('missing'):
        raise ValueError('Original photo or description is missing; private staging only.')
    rows = source_variants(source)
    images = list(source.media.filter(last_run_id=source.last_run_id, kind='image',
                                     role__in=('main', 'gallery', 'variant')))
    verified = []
    for image in images:
        try:
            verify_photo(image)
            verified.append(image)
        except (ValueError, OSError, Image.DecompressionBombError) as exc:
            # A broken EXTRA image must not hide a product with good original
            # photos. Keep its source reference and failure for staff review,
            # never substitute a logo or publish a broken gallery entry.
            image.metadata = {**image.metadata, 'verified_image': False,
                              'verification_error': str(exc)[:300]}
            image.save(using=DB, update_fields=['metadata', 'updated_at'])
    images = verified
    if not images:
        raise ValueError('No accessible verified original photo; product remains on hold.')
    counts = Counter()
    for row in rows:
        applicable = [m.pk for m in images if not m.variant_id or m.variant_id == row['id']]
        counts[apply_variant(source.pk, row, applicable)] += 1
    return dict(counts)
