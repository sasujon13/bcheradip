"""Preview/apply category normalization while retaining all original supplier data."""
from collections import Counter
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from ecommerce.models import Category, Product, ProductVariant, SupplierOffer, SupplierSourceProduct
from ecommerce.catalog_structure import classify, category_names, ensure_category, category_slug, RESEARCH_SOURCES, PROPERTY_TEMPLATES
from ecommerce.product_content import content_rows, option_review


class Command(BaseCommand):
    help = 'Preview a source-preserving taxonomy, or apply it with --apply. Prices and historical orders are untouched.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--report', default='')

    def handle(self, *args, **options):
        apply = options['apply']; paths = Counter(); counts = Counter(); review = []; supplier_counts = Counter()
        def flush_sources(batch):
            with transaction.atomic(using='ecommerce'):
                current = {s.pk:s for s in SupplierSourceProduct.objects.using('ecommerce').select_for_update().filter(pk__in=[s.pk for s in batch]).only('pk','extra')}
                for source in batch:
                    current[source.pk].extra = {**current[source.pk].extra, '_cheradip_catalog': source.extra['_cheradip_catalog']}
                SupplierSourceProduct.objects.using('ecommerce').bulk_update(list(current.values()), ['extra'], batch_size=25)

        def flush_products(batch):
            with transaction.atomic(using='ecommerce'):
                current = {p.pk:p for p in Product.objects.using('ecommerce').select_for_update().filter(pk__in=[p.pk for p in batch])}
                changed = []
                for planned in batch:
                    row = current[planned.pk]
                    if row.attributes.get('_catalog', {}).get('manual_category'): continue
                    metadata = planned.attributes['_catalog']
                    if row.category_id == planned._original_category_id:
                        row.category_id = planned.category_id
                    else:
                        metadata = {**metadata, 'manual_category': True, 'status': 'assigned'}
                    aliases = list(dict.fromkeys([*row.attributes.get('_catalog_legacy_categories', []), *planned.attributes.get('_catalog_legacy_categories', [])]))
                    row.attributes = {**row.attributes, '_catalog': metadata, '_catalog_legacy_categories': aliases}
                    if metadata['status'] == 'needs_review' and row.status == 'active': row.status = 'draft'
                    row.updated_at = timezone.now(); changed.append(row)
                if changed: Product.objects.using('ecommerce').bulk_update(changed, ['category','attributes','status','updated_at'], batch_size=25)
        source_plan = {}; source_batch = []
        for source in SupplierSourceProduct.objects.using('ecommerce').defer('raw_data').iterator(chunk_size=100):
            plan = classify(source.title, source.categories, source.description)
            source_plan[source.pk] = plan
            supplier_counts[str(source.supplier_id)] += 1
            paths[' / '.join(plan['path']) or 'Needs staff review'] += 1
            if plan['status'] == 'needs_review' and len(review) < 150:
                review.append({'source_id': source.pk, 'title': source.title, 'reason': plan['reason']})
            if apply and source.extra.get('_cheradip_catalog') != plan:
                source.extra = {**source.extra, '_cheradip_catalog': plan}; source_batch.append(source)
            if len(source_batch) >= 100:
                flush_sources(source_batch); source_batch=[]
        if source_batch: flush_sources(source_batch)
        links = dict(SupplierOffer.objects.using('ecommerce').filter(imported_product__isnull=False, source_product__isnull=False)
                     .values_list('imported_product_id', 'source_product_id'))
        category_cache = {}; target_slugs = set(); destination_counts = Counter(); product_batch = []
        products = Product.objects.using('ecommerce').select_related('category').order_by('pk')
        for product in products.iterator(chunk_size=100):
            product._original_category_id = product.category_id
            attrs = product.attributes or {}; previous = attrs.get('_catalog', {})
            if previous.get('path') and product.category.slug != category_slug(previous['path']):
                previous = {**previous, 'manual_category': True}
            plan = source_plan.get(links.get(product.pk)) or classify(product.name, [product.category.name], product.description)
            if previous.get('manual_category'):
                target_slugs.add(product.category.slug)
                parent=product.category.parent
                while parent:
                    target_slugs.add(parent.slug); parent=parent.parent
                counts['staff_categories_preserved'] += 1; continue
            if plan['path']:
                path = tuple(plan['path']); slug = category_slug(path)
                for n in range(1, len(path)+1): target_slugs.add(category_slug(path[:n]))
                destination_counts[' / '.join(path)] += 1
                if product.category.slug != slug:
                    counts['category_reassignments'] += 1
                    if apply:
                        if path not in category_cache: category_cache[path] = ensure_category(path)
                        attrs['_catalog_legacy_categories'] = list(dict.fromkeys([*attrs.get('_catalog_legacy_categories', []), product.category.slug]))
                        product.category = category_cache[path]
            else:
                counts['category_review'] += 1
                if product.status == 'active':
                    counts['active_products_held_for_review'] += 1
                    if apply: product.status = 'draft'
            # Only source records have enough data to identify missing choices.
            source = SupplierSourceProduct.objects.using('ecommerce').defer('raw_data').filter(pk=links.get(product.pk)).first() if links.get(product.pk) else None
            conflicts = {}
            variant_review = False
            if source:
                variants = list(product.variants.all())
                _, conflicts, _ = content_rows(source, attrs, variants)
                variant_review = option_review(source, variants)
                if variant_review: counts['variant_review'] += 1
                if conflicts: counts['specification_conflicts'] += 1
            metadata = {**plan, 'variant_review': variant_review, 'conflicts': conflicts}
            if apply:
                product.attributes = {**attrs, '_catalog': metadata}
                product.updated_at = timezone.now()
                product_batch.append(product)
            if len(product_batch) >= 100:
                flush_products(product_batch); product_batch=[]
            counts['products_checked'] += 1
            if counts['products_checked'] % 2000 == 0:
                self.stdout.write(json.dumps({'processed': counts['products_checked'], 'apply': apply})); self.stdout.flush()
        if product_batch: flush_products(product_batch)
        if apply:
            # Keep legacy IDs/slugs for saved category links and audit provenance.
            Category.objects.using('ecommerce').exclude(slug__in=target_slugs).update(is_active=False)
        result = {'apply': apply, 'counts': dict(counts), 'source_counts_by_supplier': dict(supplier_counts),
                  'source_category_preview': dict(paths), 'listing_category_preview': dict(destination_counts),
                  'review_samples': review, 'property_templates': PROPERTY_TEMPLATES, 'research_sources': RESEARCH_SOURCES}
        if options['report']:
            path = Path(options['report']); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(json.dumps({k:v for k,v in result.items() if k not in ('review_samples','property_templates')}, ensure_ascii=False))
