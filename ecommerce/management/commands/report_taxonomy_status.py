"""Human-readable primary/secondary category counts, without double-counting."""
from pathlib import Path
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.utils import timezone
from ecommerce.models import Category, Product


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        categories = list(Category.objects.using('ecommerce').all())
        by_id = {c.pk: c for c in categories}
        primary, linked, active = defaultdict(set), defaultdict(set), defaultdict(set)
        for pk, status, main, second in Product.objects.using('ecommerce').values_list('pk', 'status', 'category_id', 'secondary_categories__id'):
            primary[main].add(pk)
            for category in (main, second):
                if category:
                    linked[category].add(pk)
                    if status == 'active': active[category].add(pk)
        output = ['# Applied catalog taxonomy — research continues', '',
                  f'Generated: {timezone.now().isoformat()}', '',
                  'Counts are database listings, not unique supplier products. Active counts are not a promise of live stock. '
                  'Each row deduplicates primary and secondary links; category totals must not be added to calculate total inventory.', '',
                  '| Department | Product type | Primary listings | All linked listings | Active linked listings |',
                  '|---|---|---:|---:|---:|']
        for category in categories:
            if category.parent_id and linked[category.pk]:
                output.append(f'| {by_id[category.parent_id].name} | {category.name} | {len(primary[category.pk])} | {len(linked[category.pk])} | {len(active[category.pk])} |')
        pending = Product.objects.using('ecommerce').filter(attributes___catalog__status='needs_review').count()
        output.extend(['', '## Outstanding review', '', f'- {pending:,} listings marked for category review.',
            f'- {Category.objects.using("ecommerce").filter(parent__parent__isnull=False).count()} third-level categories.',
            '- Legacy broad categories remain where product evidence is unresolved; these are not approved final product types.',
            '- No products were deleted or archived by the normalization command. Original supplier data and order history remain unchanged.',
            '- Continue Research reviews categories and variants; Resume Research remains the separate competitor-price workflow.'])
        path = Path(options['output']).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(output) + '\n', encoding='utf-8')
        self.stdout.write(str(path))
