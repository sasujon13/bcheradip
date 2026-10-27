"""Export a read-only, resumable category/options review with complete source text."""
import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ecommerce.models import Product, SupplierOffer


class Command(BaseCommand):
    help = 'Export complete content for the next active listings; never changes catalog records.'

    def add_arguments(self, parser):
        parser.add_argument('--after', type=int, default=0)
        parser.add_argument('--limit', type=int, default=200)
        parser.add_argument('--report', required=True)

    def handle(self, *args, **options):
        products = list(Product.objects.using('ecommerce').filter(
            status='active', pk__gt=options['after']).select_related('category')
            .prefetch_related('variants').order_by('pk')[:max(1, min(options['limit'], 2000))])
        offers = {o.imported_product_id: o for o in SupplierOffer.objects.using('ecommerce')
                  .filter(imported_product_id__in=[p.pk for p in products])
                  .select_related('supplier', 'source_product').defer('source_product__raw_data')}
        groups = {}
        for product in products:
            offer = offers.get(product.pk)
            source = offer.source_product if offer else None
            content = {
                'title': product.name, 'category': product.category.slug,
                'supplier': offer.supplier.name if offer else None,
                'description': product.description, 'short_description': product.short_description,
                'source_title': source.title if source else None,
                'source_description': source.description if source else None,
                'source_short_description': source.short_description if source else None,
                'supplier_categories': source.categories if source else [],
                'specifications': source.specifications if source else {},
                'features': source.features if source else [],
                'source_options': source.variants if source else [],
                'listing_options': [{f'option{n}': [getattr(v, f'option{n}_name'), getattr(v, f'option{n}_value')]
                                     for n in (1, 2, 3)} for v in product.variants.all()],
                'manual_category': bool((product.attributes or {}).get('_catalog', {}).get('manual_category')),
            }
            digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            group = groups.setdefault(digest, {'content_hash': digest, 'products': [], 'content': content})
            group['products'].append({'id': product.pk, 'slug': product.slug,
                                      'source_id': source.pk if source else None,
                                      'url': source.url if source else product.source_url})
        report = {'after': options['after'], 'last_id': products[-1].pk if products else options['after'],
                  'count': len(products), 'distinct_content_groups': len(groups), 'groups': list(groups.values())}
        path = Path(options['report']).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(json.dumps({k: v for k, v in report.items() if k != 'groups'}))
        self.stdout.write(str(path))
