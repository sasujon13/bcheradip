"""Read-only full-catalog evidence inventory before two-level reclassification."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone
from ecommerce.models import Category, Product, Supplier, SupplierSourceProduct, SupplierSourceMedia


class Command(BaseCommand):
    help = 'Inventory every stored supplier product and listing without changing categories.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        folder = Path(options['output']).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        categories = list(Category.objects.using('ecommerce').values())
        parents = {c['id']: c['parent_id'] for c in categories}
        def depth(pk):
            seen = set()
            while pk is not None and pk not in seen:
                seen.add(pk)
                pk = parents.get(pk)
            return len(seen) if pk is None else -1
        suppliers = dict(Supplier.objects.using('ecommerce').values_list('pk', 'name'))
        counts, coverage, category_counts = Counter(), defaultdict(Counter), Counter()
        from ecommerce.taxonomy_proposal import candidates
        proposed, candidate_status = Counter(), Counter()
        candidate_examples = defaultdict(list)
        groups = {}
        # Explicit content fields only: never include connector settings or credentials.
        media = defaultdict(list)
        for item in SupplierSourceMedia.objects.using('ecommerce').values('product_id', 'kind', 'role', 'original_url', 'variant_id').iterator(chunk_size=1000):
            media[item.pop('product_id')].append(item)
        fields = ('id', 'supplier_id', 'external_id', 'url', 'title', 'sku',
                  'description', 'short_description', 'categories', 'specifications',
                  'features', 'variants', 'extra', 'content_hash', 'observed_at')
        with (folder / 'source-evidence.jsonl').open('w', encoding='utf-8') as output:
            for row in SupplierSourceProduct.objects.using('ecommerce').values(*fields).iterator(chunk_size=500):
                sid = row['supplier_id']
                row['extra'] = {k: v for k, v in (row['extra'] or {}).items() if k in (
                    'brand', 'brands', 'brand_id', 'tags', 'attributes', 'variations', 'size', 'color',
                    'dimensions', 'weight', 'product_weight', 'features_html', 'variant_inputs',
                    'MetaTitle', 'MetaKey', 'MetaDescription', 'product_classes')}
                row['media'] = media.get(row['id'], [])
                matches = candidates(row['title'], row['description'])
                row['candidate_paths'] = [list(path) for path in matches]
                candidate_status['single_candidate' if len(matches) == 1 else 'multiple_candidates' if matches else 'needs_research'] += 1
                for path in matches:
                    proposed[path] += 1
                    if len(candidate_examples[path]) < 3:
                        candidate_examples[path].append({'source_id': row['id'], 'title': row['title'][:160]})
                counts[sid] += 1
                for field in ('description', 'short_description', 'specifications', 'features', 'variants', 'media'):
                    if row[field]: coverage[sid][field] += 1
                content = {k: v for k, v in row.items() if k not in ('id', 'external_id', 'url', 'content_hash', 'observed_at', 'sku', 'media')}
                digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                group = groups.setdefault(digest, {'supplier': suppliers[sid], 'title': row['title'],
                    'source_categories': row['categories'], 'source_ids': [], 'review_status': 'not_reviewed'})
                group['source_ids'].append(row['id'])
                output.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
        statuses = Counter()
        with (folder / 'listing-baseline.jsonl').open('w', encoding='utf-8') as output:
            for row in Product.objects.using('ecommerce').values('id', 'slug', 'name', 'status', 'category_id', 'attributes').iterator(chunk_size=500):
                category_counts[row['category_id']] += 1
                statuses[row['status']] += 1
                output.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
        for category in categories:
            category['depth'] = depth(category['id'])
            category['listing_count'] = category_counts[category['id']]
            descendants = {category['id']}
            while True:
                expanded = descendants | {pk for pk, parent in parents.items() if parent in descendants}
                if expanded == descendants: break
                descendants = expanded
            category['subtree_listing_count'] = sum(category_counts[pk] for pk in descendants)
        summary = {'generated_at': timezone.now().isoformat(), 'mode': 'read_only_inventory_not_manual_review',
            'source_total': sum(counts.values()), 'listing_total': sum(statuses.values()),
            'listing_statuses': statuses, 'content_groups': len(groups),
            'suppliers': [{'id': sid, 'name': suppliers[sid], 'source_count': count, 'coverage': coverage[sid]} for sid, count in counts.items()],
            'category_count': len(categories), 'third_level_categories': [c['id'] for c in categories if c['depth'] > 2],
            'no_direct_listings_category_count': sum(not c['listing_count'] for c in categories),
            'empty_category_count': sum(not c['subtree_listing_count'] for c in categories),
            'root_assigned_listings': sum(c['listing_count'] for c in categories if c['depth'] == 1),
            'candidate_status': candidate_status}
        for name, value in (('summary.json', summary), ('categories-before.json', categories), ('review-queue.json', list(groups.values()))):
            (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        draft = ['# Two-level taxonomy: evidence-search draft', '',
            '**Not applied or approved.** Counts are source records matching candidate types, not final storefront counts. '
            'A record can match multiple types; all require review of descriptions and images. Unmatched records remain in the research queue.', '',
            f"Full source inventory: {sum(counts.values()):,}; shop listings: {sum(statuses.values()):,}.", '',
            '| Department | Specific product type | Candidate source records |', '|---|---|---:|']
        for (department, kind), count in sorted(proposed.items()):
            draft.append(f'| {department} | {kind} | {count} |')
        draft.extend(['', '## Remaining work', '',
            f"- No candidate yet: {candidate_status['needs_research']:,} source records.",
            f"- Multiple candidates: {candidate_status['multiple_candidates']:,} source records (some may justify secondary categories).",
            '- Single-candidate matches are NOT automatically verified assignments.',
            '- Review sets versus individual garments, child/adult and unisex evidence, bundles and misleading supplier titles.',
            '- Complete missing product types before changing the storefront. No empty proposed category is included here.',
            '- Preserve primary category plus genuine secondary links; global counts must use distinct product IDs.',
            '- Preserve source classification and old URLs; do not change publication status or historical orders.'])
        (folder / 'TAXONOMY-DRAFT.md').write_text('\n'.join(draft) + '\n', encoding='utf-8')
        (folder / 'candidate-examples.json').write_text(json.dumps([
            {'path': list(path), 'examples': examples} for path, examples in sorted(candidate_examples.items())
        ], ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(json.dumps(summary, ensure_ascii=False))
