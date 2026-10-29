"""Fast public listing rows. Text is indexed; photos stay on the existing image rules."""
import json
import sys
import threading
import time
from decimal import Decimal, InvalidOperation

from django.db import connections, transaction
from django.db.models import Case, IntegerField, Max, Q, When
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.db.utils import OperationalError
from rest_framework.exceptions import ValidationError

from .models import Category, Product, ProductImage, ProductVariant, StorefrontIndexCategory, StorefrontProductIndex
from .supplier_confirmation import MARKER


DB = 'ecommerce'
_pending = set()
_signals = False
_index_write_lock = threading.RLock()


def _running_tests():
    return 'test' in sys.argv


def _using_sqlite():
    return connections[DB].vendor == 'sqlite'


def _locked_error(exc):
    text = str(exc).lower()
    return 'locked' in text or 'busy' in text


def queue_index_refresh(product_id):
    if product_id:
        with _index_write_lock:
            _pending.add(int(product_id))


def flush_index_refresh():
    with _index_write_lock:
        ids = sorted(_pending)
        _pending.clear()
    if ids:
        refresh_storefront_index(ids)


def ensure_storefront_index():
    flush_index_refresh()
    return StorefrontProductIndex.objects.using(DB).exists()


def browse_category_ids(slug):
    categories = list(Category.objects.using(DB).values('id', 'name', 'slug', 'parent_id'))
    by_id = {row['id']: row for row in categories}
    ids = {row['id'] for row in categories if row['slug'] == slug}
    resolved_synonym = False
    from .catalog_structure import category_slug
    for pk in tuple(ids):
        row = by_id[pk]
        path = [by_id[row['parent_id']]['name'], row['name']] if row['parent_id'] else [row['name']]
        canonical_slug = category_slug(path)
        canonical_ids = {item['id'] for item in categories if item['slug'] == canonical_slug}
        if canonical_slug != slug and canonical_ids:
            resolved_synonym = True
        ids.update(canonical_ids)
    while True:
        expanded = ids | {row['id'] for row in categories if row['parent_id'] in ids}
        if expanded == ids:
            break
        ids = expanded
    return ids, resolved_synonym


def listing_queryset(request):
    flush_index_refresh()
    qs = StorefrontProductIndex.objects.using(DB).all()
    params = request.query_params
    search = (params.get('search') or '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(short_description__icontains=search) | Q(search_text__icontains=search))
    if params.get('category'):
        slug = params['category']
        ids, resolved_synonym = browse_category_ids(slug)
        membership = Q(browse_categories__category_id__in=ids)
        if not resolved_synonym:
            membership |= Q(legacy_category_slugs__icontains='"'+slug+'"')
        qs = qs.filter(membership).distinct()
    if params.get('brand'):
        qs = qs.filter(brand_slug=params['brand'])
    if params.get('in_stock') == 'true':
        qs = qs.filter(Q(stock__gt=0) | Q(allow_backorder=True, quantity_unspecified=True))
    if params.get('featured') in {'1', 'true'}:
        qs = qs.filter(featured=True)

    def price_param(name):
        raw = params.get(name)
        if raw in (None, ''):
            return None
        try:
            value = Decimal(raw)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({name: 'Enter a valid price.'})
        if not value.is_finite() or value < 0 or value > Decimal('999999999999'):
            raise ValidationError({name: 'Enter a finite, non-negative price.'})
        return value

    minimum, maximum = price_param('min_price'), price_param('max_price')
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValidationError({'max_price': 'Maximum price must be at least the minimum price.'})
    if minimum is not None:
        qs = qs.filter(price__gte=minimum)
    if maximum is not None:
        qs = qs.filter(price__lte=maximum)
    ordering = params.get('ordering')
    if ordering in {'price', '-price', 'name', '-name', 'created_at', '-created_at'}:
        field = 'listed_at' if 'created_at' in ordering else ordering.lstrip('-')
        prefix = '-' if ordering.startswith('-') else ''
        return qs.order_by(prefix + field, 'product_id')
    return qs.order_by(
        '-featured',
        Case(When(price_on_request=True, then=1), When(price__isnull=True, then=1), default=0, output_field=IntegerField()),
        Case(When(image_url='', then=1), default=0, output_field=IntegerField()),
        '-listed_at', 'product_id',
    )


def listing_price_maximum():
    flush_index_refresh()
    if StorefrontProductIndex.objects.using(DB).exists():
        return StorefrontProductIndex.objects.using(DB).aggregate(maximum=Max('price'))['maximum']
    from .views import _product_queryset
    return _product_queryset().aggregate(maximum=Max('price'))['maximum']


INDEX_WRITE_BATCH = 250


def refresh_storefront_index(product_ids=None):
    attempts = 4 if _using_sqlite() else 1
    delay = 0.05
    for attempt in range(attempts):
        try:
            with _index_write_lock:
                return _refresh_storefront_index_locked(product_ids)
        except OperationalError as exc:
            if not _locked_error(exc):
                raise
            if attempt + 1 >= attempts:
                if _running_tests():
                    return 0
                raise
            time.sleep(delay)
            delay *= 2
    return 0


def _refresh_storefront_index_locked(product_ids=None):
    from .supplier_pilot import public_product_ids
    from .views import _product_queryset
    public = set(public_product_ids()) | set(
        Product.objects.using(DB).filter(status='active', supplier_offer__isnull=True).values_list('pk', flat=True))
    if product_ids is None:
        _pending.clear()
        wanted = public
        StorefrontProductIndex.objects.using(DB).exclude(product_id__in=wanted or [0]).delete()
        ids = sorted(wanted)
    else:
        wanted = public.intersection(int(pk) for pk in product_ids)
        StorefrontProductIndex.objects.using(DB).filter(product_id__in=product_ids).exclude(product_id__in=wanted or [0]).delete()
        ids = sorted(wanted)
    written = 0
    for start in range(0, len(ids), INDEX_WRITE_BATCH):
        written += _write_index_rows(ids[start:start + INDEX_WRITE_BATCH], _product_queryset)
    if product_ids is None:
        from .storefront_taxonomy import refresh_taxonomy_snapshot
        refresh_taxonomy_snapshot()
    return written


def _legacy_slug_text(attrs):
    raw = (attrs or {}).get('_catalog_legacy_categories') or []
    if isinstance(raw, str):
        return raw
    return json.dumps(list(raw))


def _write_index_rows(ids, product_queryset):
    if not ids:
        return 0
    annotated = {
        row.pk: row for row in product_queryset(public_ids=list(ids)).filter(pk__in=ids).select_related('category', 'brand')
    }
    secondary = {}
    for product_id, category_id in Product.secondary_categories.through.objects.using(DB).filter(
            product_id__in=ids).values_list('product_id', 'category_id'):
        secondary.setdefault(product_id, set()).add(category_id)
    skus = {}
    for product_id, sku in ProductVariant.objects.using(DB).filter(product_id__in=ids, is_active=True).values_list('product_id', 'sku'):
        skus.setdefault(product_id, []).append(sku)
    written = 0
    with transaction.atomic(using=DB):
        for product_id, row in annotated.items():
            attrs = row.attributes or {}
            catalog = attrs.get('_catalog') or {}
            preview = bool(attrs.get('_catalog_price_preview'))
            search = ' '.join(part for part in [
                row.name, row.tags, getattr(row.brand, 'name', '') or '', *skus.get(product_id, [])[:8],
            ] if part)[:2000]
            listing, _ = StorefrontProductIndex.objects.using(DB).update_or_create(
                product_id=product_id,
                defaults={
                    'name': row.name,
                    'slug': row.slug,
                    'short_description': row.short_description or '',
                    'search_text': search,
                    'category_id': row.category_id,
                    'category_name': row.category.name if row.category_id else '',
                    'brand_id': row.brand_id,
                    'brand_name': row.brand.name if row.brand_id else '',
                    'brand_slug': row.brand.slug if row.brand_id else '',
                    'featured': row.featured,
                    'is_sample': row.is_sample,
                    'tags': row.tags or '',
                    'price': row.price,
                    'compare_at_price': row.compare_at_price,
                    'stock': int(row.stock or 0),
                    'image_url': row.image_url or '',
                    'default_variant_id': row.default_variant_id,
                    'allow_backorder': bool(row.allow_backorder),
                    'discount_percent': _discount(row),
                    'purchasable': not preview and not catalog.get('variant_review', False),
                    'price_on_request': preview,
                    'quantity_unspecified': bool(attrs.get(MARKER)),
                    'listed_at': row.created_at,
                    'legacy_category_slugs': _legacy_slug_text(attrs),
                },
            )
            browse = {row.category_id, *secondary.get(product_id, set())}
            browse.discard(None)
            StorefrontIndexCategory.objects.using(DB).filter(listing=listing).exclude(category_id__in=browse or [0]).delete()
            for category_id in browse:
                StorefrontIndexCategory.objects.using(DB).get_or_create(listing=listing, category_id=category_id)
            written += 1
    return written


def _discount(row):
    rule = (row.attributes or {}).get('_retail_pricing', {}).get(str(getattr(row, 'default_variant_id', None)), {})
    if isinstance(rule, dict) and rule.get('mode') in {'sale', 'reserve'}:
        try:
            return int(Decimal(str(rule.get('discount_percent', '10'))))
        except Exception:
            pass
    if row.price is not None and row.compare_at_price and row.compare_at_price > row.price:
        return int((row.compare_at_price - row.price) * 100 / row.compare_at_price)
    return 0


def _queue_product(sender, instance, **kwargs):
    queue_index_refresh(instance.pk)


def _queue_related(sender, instance, **kwargs):
    queue_index_refresh(getattr(instance, 'product_id', None))


def _queue_secondary(sender, instance, **kwargs):
    queue_index_refresh(instance.pk)


def connect_signals():
    global _signals
    if _signals:
        return
    post_save.connect(_queue_product, sender=Product, dispatch_uid='storefront-index-product')
    post_delete.connect(_queue_product, sender=Product, dispatch_uid='storefront-index-product-del')
    post_save.connect(_queue_related, sender=ProductVariant, dispatch_uid='storefront-index-variant')
    post_delete.connect(_queue_related, sender=ProductVariant, dispatch_uid='storefront-index-variant-del')
    post_save.connect(_queue_related, sender=ProductImage, dispatch_uid='storefront-index-image')
    post_delete.connect(_queue_related, sender=ProductImage, dispatch_uid='storefront-index-image-del')
    m2m_changed.connect(_queue_secondary, sender=Product.secondary_categories.through, dispatch_uid='storefront-index-secondary')
    _signals = True
