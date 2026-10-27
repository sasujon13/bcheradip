"""Release obsolete option-mapping holds within a completed catalog review."""
from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone

from ecommerce.models import Product
from ecommerce.product_content import description_colors, description_sizes, option_review


class Command(BaseCommand):
    help = 'Preview/resolve old option holds where the reviewed supplier content supplies explicit choices.'

    def add_arguments(self, parser):
        parser.add_argument('--after', type=int, default=0)
        parser.add_argument('--through-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        counts = Counter()
        examples = []
        products = Product.objects.using('ecommerce').filter(
            status='active', pk__gt=options['after'], pk__lte=options['through_id'],
            attributes___catalog__variant_review=True,
        ).select_related('supplier_offer__source_product').prefetch_related('variants').order_by('pk')
        for product in products:
            counts['reviewed_holds'] += 1
            offer = getattr(product, 'supplier_offer', None)
            source = offer.source_product if offer else None
            if not source:
                counts['unresolved'] += 1
                continue
            product._content_source = source
            variants = list(product.variants.all())
            sizes = description_sizes(product, variants)
            colors = description_colors(product, variants)
            if not (sizes or colors) or option_review(source, variants,
                    allow_description_size=bool(sizes), allow_description_color=bool(colors)):
                counts['unresolved'] += 1
                continue
            counts['resolvable'] += 1
            if len(examples) < 10:
                examples.append({'id': product.pk, 'sizes': sizes, 'colors': colors})
            if options['apply']:
                attrs = product.attributes or {}
                attrs = {**attrs, '_catalog': {**attrs.get('_catalog', {}), 'variant_review': False,
                    'choices_reviewed_at': timezone.now().isoformat(),
                    'choices_source_hash': source.content_hash}}
                # Keep a concurrent staff edit intact. No stock, price, status,
                # source SKU or historical order is modified by this operation.
                changed = Product.objects.using('ecommerce').filter(
                    pk=product.pk, updated_at=product.updated_at).update(attributes=attrs, updated_at=timezone.now())
                counts['updated' if changed else 'concurrent_edit_skipped'] += 1
        self.stdout.write(str({'apply': options['apply'], 'counts': dict(counts), 'examples': examples}))
