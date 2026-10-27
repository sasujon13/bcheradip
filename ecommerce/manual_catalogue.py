"""Owner-authorised catalogue launch; research decisions remain independent.

Keep All deliberately waives screening, NOT authenticity of price/stock claims.
No supplier purchase is made here. Source references stay in private offer rows.
"""
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Exists, OuterRef, F
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify
from .models import (Product, ProductVariant, ProductImage, Category, SupplierOffer,
                     SupplierPolicy, SupplierJob,DeliverySettings)

DB = 'ecommerce'
MARKER = 'manual_supplier_catalogue'


def approved_offers():
    from .supplier_service import policy
    from django.utils import timezone
    from datetime import timedelta
    return Q(state='ready', current_decision__state='ready',
             current_decision__approved_at__isnull=False,
             current_decision__created_at__gte=timezone.now()-timedelta(days=policy().evidence_days))


def eligible_offers(mode=None):
    mode = mode or SupplierPolicy.objects.using(DB).filter(pk=1).values_list('catalogue_mode', flat=True).first()
    qs = SupplierOffer.objects.using(DB).filter(supplier__enabled=True).exclude(state='excluded')
    return qs if mode == 'all' else qs.filter(approved_offers())


def purchasable_offers(mode=None, *, include_equivalent_alternatives=False):
    """Use last known supplier availability without hiding a listing at 24 hours.

    Observation age is reported separately and triggers a background refresh.
    A positive old observation is not presented as a new supplier confirmation.
    """
    now = timezone.now()
    from .supplier_confirmation import MARKER
    from .supplier_media import source_image_url_condition
    photos = ProductImage.objects.using(DB).filter(
        product_id=OuterRef('imported_product_id'), source_media__product_id=OuterRef('source_product_id'),
        source_media__last_run_id=OuterRef('source_product__last_run_id'), source_media__kind='image',
        source_media__role__in=('main', 'gallery', 'variant'), source_media__metadata__verified_image=True).filter(source_image_url_condition())
    exact = Q(allow_backorder=False,stock__gt=0,stock__lte=OuterRef('quantity'))
    confirmation = Q(allow_backorder=True,stock=0,product__supplier_offer__quantity__isnull=True,
                     **{'product__attributes__'+MARKER:True})
    variants = ProductVariant.objects.using(DB).filter(
        product_id=OuterRef('imported_product_id'), is_active=True, currency='BDT', price__gt=0,
        cost_price=OuterRef('source_price')).filter(exact | confirmation)
    duplicates=Q(imported_product__attributes___catalog_duplicate_of_slug__isnull=True)
    if include_equivalent_alternatives:
        duplicates |= Q(imported_product__attributes___supplier_equivalence__previous_status='active')
    return eligible_offers(mode).filter(
        imported_product__attributes__supplier_publication_ready=True,
        supplier__terms_confirmed=True, excluded_reason='', source_price__gt=0, currency='BDT',
        single_unit=True, availability='in_stock',
        observed_at__isnull=False, observed_at__lte=now,
        source_product__observed_at__lte=now,
        source_product__quality__missing=[],
    ).filter(duplicates).exclude(Q(observed_at__lte=F('source_product__observed_at')) & (
        (Q(source_product__stock__status__isnull=False) & Q(source_product__stock__status__in=('out_of_stock','missing','unconfirmed'))) |
        (Q(source_product__stock__quantity__isnull=False) & ~Q(source_product__stock__quantity=None) & Q(source_product__stock__quantity__lte=0)) |
        (Q(supplier_id=2) & Q(source_product__raw_data__product__status__isnull=False) & ~Q(source_product__raw_data__product__status='ACTIVE'))
    )).filter(Q(quantity__gt=0) | Q(quantity__isnull=True,**{'imported_product__attributes__'+MARKER:True})).exclude(imported_product__description='').annotate(
        has_original_photo=Exists(photos), has_orderable_variant=Exists(variants)
    ).filter(has_original_photo=True, has_orderable_variant=True)


def public_ids():
    return purchasable_offers().filter(imported_product__attributes__manual_supplier_catalogue=True).values_list('imported_product_id', flat=True)


def price_preview_ids(include_inactive=False):
    """Owner-authorised visible listings with real photos, without invented prices."""
    from .models import SupplierSourceMedia
    from .supplier_media import source_image_url_condition
    photos = ProductImage.objects.using(DB).filter(product_id=OuterRef('pk'),
        source_media__product_id=OuterRef('supplier_offer__source_product_id'),
        source_media__last_run_id=OuterRef('supplier_offer__source_product__last_run_id'),
        source_media__metadata__verified_image=True).filter(source_image_url_condition())
    qs = Product.objects.using(DB).filter(attributes___catalog_price_preview=True,
        supplier_offer__supplier__enabled=True, supplier_offer__excluded_reason='').exclude(
        supplier_offer__availability__in=('out_of_stock','missing')).filter(attributes___catalog_duplicate_of_slug__isnull=True).exclude(description='').annotate(
            preview_has_photo=Exists(photos)).filter(preview_has_photo=True)
    if not include_inactive: qs = qs.filter(status='active')
    return qs.values_list('pk',flat=True)


def is_manual(product):
    return bool((product.attributes or {}).get(MARKER))


def checkout_check(variant, quantity):
    offer = SupplierOffer.objects.using(DB).get(imported_product_id=variant.product_id)
    if not purchasable_offers().filter(pk=offer.pk).exists():
        raise ValueError('This product needs a current supplier photo, buying price and available stock check. Please refresh your cart.')
    if offer.source_price is None or offer.source_price <= 0 or offer.currency != 'BDT' or variant.price <= 0:
        raise ValueError('This product needs price confirmation before ordering.')
    from .supplier_confirmation import quantity_unspecified
    if quantity_unspecified(variant) and offer.availability == 'in_stock' and offer.quantity is None and variant.stock == 0:
        return offer
    if (offer.availability != 'in_stock' or offer.quantity is None or offer.quantity < quantity or
            variant.allow_backorder or not variant.is_active or variant.stock < quantity or variant.cost_price != offer.source_price):
        raise ValueError('The requested supplier quantity is unavailable. Please update your cart.')
    return offer


@transaction.atomic(using=DB)
def import_offer(offer_id):
    """Idempotent incremental import. Never replaces staff-edited listing fields."""
    from .supplier_service import costs_for
    from .pricing import calculate_price
    offer = SupplierOffer.objects.using(DB).select_for_update().get(pk=offer_id)
    if offer.state == 'excluded':
        return 'excluded'
    if not offer.title.strip():
        return 'missing_title'
    if offer.imported_product_id:
        return 'existing'
    from .catalog_structure import classify, ensure_category
    source = offer.source_product
    category_plan = classify(offer.title, source.categories if source else [(offer.identity or {}).get('category', '')], source.description if source else '')
    if category_plan['path']:
        category = ensure_category(tuple(category_plan['path']))
    else:
        category, _ = Category.objects.using(DB).get_or_create(slug='catalog-review', defaults={'name': 'Pending classification', 'is_active': False})
    from django.utils.html import strip_tags
    from html import unescape
    source = offer.source_product
    from .supplier_recollection import preferred_description
    product = Product.objects.using(DB).create(name=offer.title[:255],
        slug=f'supplier-{offer.supplier_id}-{offer.pk}', category=category, status='draft',
        description=preferred_description(source) if source else '',
        short_description=str((offer.identity or {}).get('short_description') or '')[:500],
        attributes={MARKER: True, '_catalog': category_plan})
    offer.imported_product = product
    offer.save(using=DB, update_fields=['imported_product', 'updated_at'])
    priced = offer.source_price is not None and offer.source_price > 0 and offer.currency == 'BDT'
    if priced:
        costs = costs_for(offer)
        suggestion = calculate_price(offer.source_price, {k: str(costs[k]) for k in
            ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs')}, subsidy_enabled=False,
            rules=DeliverySettings.current().pricing_rules)
        ProductVariant.objects.using(DB).create(product=product, sku=f'CATALOGUE-{offer.pk}',
            title=str((offer.identity or {}).get('variant') or 'Default')[:160],
            price=suggestion['suggested_price'], cost_price=offer.source_price,
            stock=max(0, offer.quantity or 0) if offer.availability not in ('out_of_stock', 'missing') else 0,
            allow_backorder=False,
            weight_grams=offer.weight_grams or 0)
    images = list(dict.fromkeys(str(url) for url in (offer.preview_images or []) if str(url).startswith(('https://', 'http://'))))
    media = {m.original_url: m for m in source.media.filter(last_run_id=source.last_run_id, kind='image', metadata__verified_image=True)} if source else {}
    ProductImage.objects.using(DB).bulk_create([ProductImage(product=product, url=url, source_media=media.get(url), alt_text=product.name, position=n) for n,url in enumerate(images) if len(url) <= 1000])
    if priced:
        floor = offer.source_price + sum((costs[k] for k in ('ads_cost', 'packaging_cost', 'returns_allowance', 'other_costs', 'fees', 'taxes')), Decimal('0'))
        Product.objects.using(DB).filter(pk=product.pk).update(attributes={MARKER: True, 'supplier_publication_ready': Decimal(suggestion['suggested_price']) > floor})
    # QuerySet update is intentional: the explicit catalogue policy is the release,
    # not the separate individually verified pilot release.
    status = 'active' if eligible_offers().filter(pk=offer.pk).exists() else 'archived'
    Product.objects.using(DB).filter(pk=product.pk).update(status=status)
    return 'published' if status == 'active' else 'archived'


def queue_imports(actor_id=None):
    from .models import Supplier
    jobs = []
    for supplier in Supplier.objects.using(DB).filter(enabled=True):
        if SupplierJob.objects.using(DB).filter(supplier=supplier, action='publish_catalogue', status__in=['queued','running','cancel_requested']).exists():
            continue
        ids = list(eligible_offers('all').filter(supplier=supplier, imported_product__isnull=True).values_list('pk', flat=True))
        if ids:
            job = SupplierJob.objects.using(DB).create(supplier=supplier, action='publish_catalogue',
                actor_id=actor_id, total=len(ids), payload={'ids': ids}, activity='Import collected identities for manual fulfilment')
            jobs.append(str(job.pk))
    return jobs
