"""Preview/apply source-backed two-level mappings; preserve unresolved listings."""
import json
from collections import Counter
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from ecommerce.models import Category, Product, SupplierOffer
from ecommerce.taxonomy_proposal import normalized_classification
from ecommerce.catalog_structure import ensure_category, category_slug


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--report', required=True)

    def handle(self, *args, **options):
        # Original relationship snapshot is written BEFORE any changes.
        path = Path(options['report']).resolve()
        if path.exists():
            from django.core.management.base import CommandError
            raise CommandError('Choose a new report filename; prior snapshots are never overwritten.')
        path.parent.mkdir(parents=True, exist_ok=True)
        categories = list(Category.objects.using('ecommerce').values('id', 'name', 'slug', 'parent_id', 'is_active'))
        by_id = {c['id']: c for c in categories}
        offers = {o.imported_product_id: o for o in SupplierOffer.objects.using('ecommerce').exclude(imported_product_id=None)
                  .select_related('source_product').defer('source_product__raw_data')}
        rows, counts, totals = [], Counter(), Counter()
        for product in Product.objects.using('ecommerce').prefetch_related('secondary_categories').order_by('pk').iterator(chunk_size=500):
            meta = (product.attributes or {}).get('_catalog', {})
            offer = offers.get(product.pk)
            source = offer.source_product if offer else None
            plan = normalized_classification(source.title if source else product.name,
                source.categories if source else [], source.description if source else product.description)
            if meta.get('manual_category'):
                plan = {'path': [], 'status': 'manual_preserved', 'reason': 'Staff-pinned category'}
            rows.append({'id': product.pk, 'slug': product.slug, 'name': product.name, 'status': product.status,
                'category_id': product.category_id, 'updated_at': product.updated_at.isoformat(),
                'attributes_before': product.attributes, 'plan': plan})
            rows[-1]['secondary_categories_before'] = [c.pk for c in product.secondary_categories.all()]
            counts[plan['status']] += 1
            if plan['path']: totals[' / '.join(plan['path'])] += 1
        report = {'apply': options['apply'], 'created_at': timezone.now().isoformat(), 'categories_before': categories,
                  'counts': counts, 'primary_destination_counts': totals, 'products': rows}
        path.write_text(json.dumps(report, ensure_ascii=False, default=str), encoding='utf-8')
        changed, skipped, unchanged, queued = 0, 0, 0, 0
        if options['apply']:
            cache = {}
            for row in rows:
                plan = row['plan']
                if not plan['path']:
                    if plan['status'] == 'needs_review':
                        attrs = dict(row['attributes_before'] or {})
                        old_meta = attrs.get('_catalog', {})
                        if old_meta.get('status') != 'needs_review' or old_meta.get('version') != 2:
                            attrs['_catalog'] = {**old_meta, **plan}
                            queued += Product.objects.using('ecommerce').filter(pk=row['id'], updated_at=row['updated_at']).update(
                                attributes=attrs, updated_at=timezone.now())
                    continue
                previous = (row['attributes_before'] or {}).get('_catalog', {})
                secondary_slugs = {by_id[pk]['slug'] for pk in row['secondary_categories_before'] if pk in by_id}
                if (previous.get('version') == 2 and previous.get('path') == plan['path']
                        and by_id[row['category_id']]['slug'] == category_slug(plan['path'])
                        and all(category_slug(p) in secondary_slugs for p in plan.get('secondary_paths', []))):
                    unchanged += 1
                    continue
                with transaction.atomic(using='ecommerce'):
                    current = Product.objects.using('ecommerce').select_for_update().get(pk=row['id'])
                    if current.updated_at.isoformat() != row['updated_at']:
                        skipped += 1
                        continue
                    key = tuple(plan['path'])
                    if key not in cache: cache[key] = ensure_category(key)
                    attrs = dict(current.attributes or {})
                    old = by_id.get(current.category_id)
                    aliases = list(attrs.get('_catalog_legacy_categories', []))
                    visited = set()
                    while old and old['id'] not in visited:
                        visited.add(old['id']); aliases.append(old['slug']); old = by_id.get(old['parent_id'])
                    attrs['_catalog_legacy_categories'] = list(dict.fromkeys(aliases))
                    attrs['_catalog'] = {**attrs.get('_catalog', {}), **plan, 'mapped_at': timezone.now().isoformat()}
                    Product.objects.using('ecommerce').filter(pk=current.pk).update(category=cache[key], attributes=attrs, updated_at=timezone.now())
                    # Add only justified links; never erase staff-managed secondary links.
                    for secondary in plan.get('secondary_paths', []):
                        skey = tuple(secondary)
                        if skey not in cache: cache[skey] = ensure_category(skey)
                        current.secondary_categories.add(cache[skey])
                    changed += 1
            # Flatten legacy leaf paths without deleting their relationships or URLs.
            for category in Category.objects.using('ecommerce').select_related('parent').filter(parent__parent__isnull=False):
                root, seen = category.parent, {category.pk}
                while root.parent_id and root.pk not in seen:
                    seen.add(root.pk); root = root.parent
                if root.pk not in seen:
                    Category.objects.using('ecommerce').filter(pk=category.pk).update(parent_id=root.pk)
            for category in Category.objects.using('ecommerce').filter(parent__isnull=False):
                if not category.products.exists() and not category.secondary_products.exists():
                    Category.objects.using('ecommerce').filter(pk=category.pk).update(is_active=False)
            # Source classifications, prices, inventory, publication and orders stay untouched.
        result = {'apply': options['apply'], 'counts': counts, 'mapped': changed, 'concurrent_changes_skipped': skipped,
                  'already_mapped': unchanged,
                  'queued_for_category_review': queued,
                  'third_level_remaining': Category.objects.using('ecommerce').filter(parent__parent__isnull=False).count(),
                  'report': str(path)}
        result['listing_count_after'] = Product.objects.using('ecommerce').count()
        result['secondary_links'] = Product.secondary_categories.through.objects.using('ecommerce').count()
        result['publication_counts_before'] = dict(Counter(row['status'] for row in rows))
        result['publication_counts_after'] = dict(Counter(Product.objects.using('ecommerce').values_list('status', flat=True)))
        from django.db.models import Count, Q
        result['categories_after'] = list(Category.objects.using('ecommerce').values('id', 'name', 'slug', 'parent_id', 'is_active').annotate(
            primary_count=Count('products', distinct=True), active_primary_count=Count('products', filter=Q(products__status='active'), distinct=True),
            secondary_count=Count('secondary_products', distinct=True)))
        path.with_suffix('.result.json').write_text(json.dumps(result, ensure_ascii=False, default=str), encoding='utf-8')
        self.stdout.write(json.dumps({k: v for k, v in result.items() if k != 'categories_after'}))
