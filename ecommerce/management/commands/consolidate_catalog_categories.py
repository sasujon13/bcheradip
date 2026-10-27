"""Preview and consolidate synonymous category paths without changing inventory."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ecommerce.category_normalization import canonical_path, specialized_path
from ecommerce.catalog_structure import ensure_category
from ecommerce.models import Category, Product, SupplierOffer


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--report', required=True)

    def handle(self, *args, **options):
        output = Path(options['report']).resolve()
        if output.exists():
            raise CommandError('Use a new snapshot filename.')
        categories = list(Category.objects.using('ecommerce').all())
        by_id = {c.pk: c for c in categories}

        def path_for(pk):
            c = by_id[pk]
            return (by_id[c.parent_id].name, c.name) if c.parent_id else (c.name,)

        # Preserve independent supplier offers and their exact option identities.
        offers = {o.imported_product_id: o for o in SupplierOffer.objects.using('ecommerce')
            .exclude(imported_product=None).select_related('source_product').defer('source_product__raw_data')}
        products = list(Product.objects.using('ecommerce').prefetch_related('secondary_categories', 'variants').order_by('pk'))
        plans, counts, duplicate_groups = [], Counter(), defaultdict(list)
        for p in products:
            old = path_for(p.category_id)
            offer = offers.get(p.pk)
            source = offer.source_product if offer else None
            title = source.title if source else p.name
            desc = source.description if source else p.description
            meta = (p.attributes or {}).get('_catalog', {})
            new = canonical_path(old) if meta.get('manual_category') else specialized_path(old, title, desc)
            secondary = sorted({canonical_path(path_for(c.pk)) for c in p.secondary_categories.all()} - {new})
            before_secondary = sorted(path_for(c.pk) for c in p.secondary_categories.all())
            if new != old or secondary != before_secondary:
                plans.append({'id': p.pk, 'slug': p.slug, 'old_path': old, 'new_path': new,
                    'category_before': p.category_id, 'secondary_before': [c.pk for c in p.secondary_categories.all()],
                    'secondary_paths': secondary, 'attributes_before': p.attributes, 'updated_at': p.updated_at.isoformat()})
                counts[' / '.join(old) + ' → ' + ' / '.join(new)] += 1
            if source:
                # Same title alone cannot identify duplicates: supplier variants,
                # prices and fulfillment identity must also agree.
                variants = sorted((v.option1_name, v.option1_value, v.option2_name, v.option2_value,
                    v.option3_name, v.option3_value, str(v.price), str(v.cost_price), v.stock, v.is_active)
                    for v in p.variants.all())
                fingerprint = json.dumps([source.pk, p.name, p.source_url, variants], sort_keys=True)
                duplicate_groups[fingerprint].append(p.pk)
        duplicates = [ids for ids in duplicate_groups.values() if len(ids) > 1]
        before = dict(Counter(p.status for p in products))
        report = {'created_at': timezone.now().isoformat(), 'apply': options['apply'],
            'publication_before': before, 'listing_count': len(products), 'moves': dict(counts),
            'products': plans, 'exact_duplicate_candidates': duplicates,
            'categories_before': [{'id': c.pk, 'name': c.name, 'slug': c.slug, 'parent_id': c.parent_id,
                'is_active': c.is_active} for c in categories]}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, default=str), encoding='utf-8')
        changed = 0
        if options['apply']:
            destinations = {}

            def destination_for(path):
                key = tuple(path)
                if key not in destinations:
                    destinations[key] = ensure_category(key)
                return destinations[key]

            with transaction.atomic(using='ecommerce'):
                for row in plans:
                    p = Product.objects.using('ecommerce').select_for_update().get(pk=row['id'])
                    if p.updated_at.isoformat() != row['updated_at']:
                        raise CommandError('Concurrent product edit detected; no category changes committed. Preview again.')
                    destination = destination_for(row['new_path'])
                    attrs = dict(p.attributes or {})
                    old_ids = [row['category_before'], *row['secondary_before']]
                    aliases = list(attrs.get('_catalog_legacy_categories', []))
                    for pk in old_ids:
                        c = by_id[pk]
                        aliases.append(c.slug)
                        if c.parent_id: aliases.append(by_id[c.parent_id].slug)
                    attrs['_catalog_legacy_categories'] = list(dict.fromkeys(aliases))
                    metadata = dict(attrs.get('_catalog', {}))
                    metadata.update(path=list(row['new_path']), category_consolidated_at=timezone.now().isoformat())
                    if len(row['new_path']) == 1:
                        metadata.update(status='needs_review', reason='Specific product type requires source evidence')
                    attrs['_catalog'] = metadata
                    Product.objects.using('ecommerce').filter(pk=p.pk).update(category=destination,
                        attributes=attrs, updated_at=timezone.now())
                    p.secondary_categories.set([destination_for(path).pk for path in row['secondary_paths']])
                    changed += 1
                # Retain old category records for old bookmarks and audit history.
                # Only empty branches are removed from storefront navigation.
                for c in Category.objects.using('ecommerce').filter(parent__isnull=False):
                    if not c.products.exists() and not c.secondary_products.exists():
                        Category.objects.using('ecommerce').filter(pk=c.pk).update(is_active=False)
                for c in Category.objects.using('ecommerce').filter(parent=None):
                    if not c.products.exists() and not c.secondary_products.exists() and not c.children.filter(is_active=True).exists():
                        Category.objects.using('ecommerce').filter(pk=c.pk).update(is_active=False)
                after = dict(Counter(Product.objects.using('ecommerce').values_list('status', flat=True)))
                if before != after or Product.objects.using('ecommerce').count() != len(products):
                    raise CommandError('Inventory invariant failed; category changes rolled back.')
        result = {'changed': changed, 'proposed': len(plans), 'publication_counts': before,
            'listing_count': len(products), 'exact_duplicate_candidates': duplicates,
            'third_level_categories': Category.objects.using('ecommerce').filter(parent__parent__isnull=False).count(),
            'moves': dict(counts), 'report': str(output)}
        output.with_suffix('.result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        self.stdout.write(json.dumps({k: v for k, v in result.items() if k != 'moves'}))
