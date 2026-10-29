"""Last-used shop taxonomy snapshot. Nav reads JSON; counts come from the listing index."""
import sys
import threading
from datetime import timedelta

from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.utils import timezone

from .models import Category, Product, StorefrontIndexCategory, StorefrontLastUsedCategory, StorefrontProductIndex, StorefrontTaxonomySnapshot
from .storefront_index import flush_index_refresh


DB = 'ecommerce'
SNAPSHOT_KEY = 'storefront'
SNAPSHOT_STALE = timedelta(seconds=60)
LAST_USED_KEEP = 40
_signals = False
_refresh_lock = threading.Lock()


def _running_tests():
    return 'test' in sys.argv


def taxonomy_categories():
    """Return serializer-shaped category rows. Tests always rebuild; live serves the snapshot."""
    flush_index_refresh()
    if _running_tests():
        return refresh_taxonomy_snapshot()['categories']
    row = StorefrontTaxonomySnapshot.objects.using(DB).filter(key=SNAPSHOT_KEY).first()
    categories = list((row.payload or {}).get('categories') or []) if row else []
    if categories:
        if row and timezone.now() - row.updated_at >= SNAPSHOT_STALE:
            threading.Thread(target=refresh_taxonomy_snapshot, daemon=True).start()
        return categories
    return refresh_taxonomy_snapshot()['categories']


def refresh_taxonomy_snapshot():
    with _refresh_lock:
        return _refresh_taxonomy_snapshot_locked()


def _refresh_taxonomy_snapshot_locked():
    categories = _taxonomy_from_index() if StorefrontProductIndex.objects.using(DB).exists() else []
    if not categories:
        categories = _taxonomy_from_products()
    last_used = list(
        StorefrontLastUsedCategory.objects.using(DB).order_by('-used_at').values_list('slug', flat=True)[:20])
    payload = {'categories': categories, 'last_used_slugs': last_used}
    StorefrontTaxonomySnapshot.objects.using(DB).update_or_create(
        key=SNAPSHOT_KEY, defaults={'payload': payload})
    return payload


def invalidate_taxonomy_snapshot():
    StorefrontTaxonomySnapshot.objects.using(DB).filter(key=SNAPSHOT_KEY).delete()


def remember_last_used(slug):
    slug = (slug or '').strip()
    if not slug:
        return
    category = Category.objects.using(DB).filter(slug=slug, is_active=True).select_related('parent').first()
    if not category:
        return
    parent = category.parent if category.parent_id else category
    children = list(Category.objects.using(DB).filter(parent=parent, is_active=True))
    child_slugs = [child.slug for child in children]
    now = timezone.now()
    for item in [parent, *children]:
        StorefrontLastUsedCategory.objects.using(DB).update_or_create(
            slug=item.slug,
            defaults={
                'name': item.name,
                'parent_slug': parent.slug if item.pk != parent.pk else '',
                'child_slugs': child_slugs if item.pk == parent.pk else [],
                'used_at': now,
            },
        )
    StorefrontLastUsedCategory.objects.using(DB).filter(slug=slug).update(used_at=now)
    keep = list(
        StorefrontLastUsedCategory.objects.using(DB).order_by('-used_at').values_list('pk', flat=True)[:LAST_USED_KEEP])
    StorefrontLastUsedCategory.objects.using(DB).exclude(pk__in=keep or [0]).delete()


def _taxonomy_from_index():
    categories = list(Category.objects.using(DB).filter(is_active=True).values(
        'id', 'name', 'slug', 'parent_id', 'description', 'image_url', 'sort_order', 'is_active'))
    if not categories:
        return []
    by_id = {row['id']: row for row in categories}
    memberships = {pk: set() for pk in by_id}
    for listing_id, category_id in StorefrontIndexCategory.objects.using(DB).values_list('listing_id', 'category_id'):
        visited = set()
        while category_id in by_id and category_id not in visited:
            visited.add(category_id)
            memberships[category_id].add(listing_id)
            category_id = by_id[category_id]['parent_id']
    return _rows_with_counts(categories, memberships)


def _taxonomy_from_products():
    categories = list(Category.objects.using(DB).filter(is_active=True))
    by_id = {category.pk: category for category in categories}
    from .supplier_pilot import public_product_ids
    visible = Product.objects.using(DB).filter(status='active').filter(
        Q(supplier_offer__isnull=True) | Q(pk__in=public_product_ids()))
    memberships = {pk: set() for pk in by_id}

    def add_rows(rows):
        for product_id, category_id in rows:
            visited = set()
            while category_id in by_id and category_id not in visited:
                visited.add(category_id)
                memberships[category_id].add(product_id)
                category_id = by_id[category_id].parent_id

    add_rows(visible.values_list('pk', 'category_id'))
    add_rows(visible.values_list('pk', 'secondary_categories'))
    source = [{
        'id': category.pk,
        'name': category.name,
        'slug': category.slug,
        'parent_id': category.parent_id,
        'description': category.description,
        'image_url': category.image_url,
        'sort_order': category.sort_order,
        'is_active': category.is_active,
    } for category in categories]
    return _rows_with_counts(source, memberships)


def _rows_with_counts(categories, memberships):
    rows = []
    for category in categories:
        count = len(memberships.get(category['id']) or ())
        if count <= 0:
            continue
        row = dict(category)
        row['product_count'] = count
        rows.append(row)
    return rows


def _invalidate_taxonomy(sender, **kwargs):
    invalidate_taxonomy_snapshot()


def connect_taxonomy_signals():
    global _signals
    if _signals:
        return
    post_save.connect(_invalidate_taxonomy, sender=Category, dispatch_uid='storefront-taxonomy-category')
    post_delete.connect(_invalidate_taxonomy, sender=Category, dispatch_uid='storefront-taxonomy-category-del')
    _signals = True
