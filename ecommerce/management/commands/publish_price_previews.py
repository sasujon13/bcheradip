"""Owner-authorised visibility for unpriced products with original supplier media."""
import json
from collections import Counter
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from ecommerce.models import SupplierOffer, Product, ProductImage
from ecommerce.supplier_source_publish import verify_photo
from ecommerce.supplier_recollection import preferred_description
from ecommerce.supplier_connectors import RESTRICTED


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--after-id', type=int, default=0)
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        qs = SupplierOffer.objects.using('ecommerce').filter(
            Q(source_price=None) | Q(source_price__lte=0), pk__gt=options['after_id'],
            supplier__enabled=True, excluded_reason='', source_product__isnull=False,
            imported_product__isnull=False).exclude(state='excluded').exclude(availability__in=('out_of_stock','missing')).select_related('source_product','imported_product').order_by('pk')
        if options['limit']: qs = qs[:options['limit']]
        counts, last = Counter(), options['after_id']
        # Keyset-sized queryset pages should be supplied for long resumptions.
        for offer in qs.iterator(chunk_size=100):
            last = offer.pk
            source, product = offer.source_product, offer.imported_product
            if RESTRICTED.search(source.title) or source.quality.get('missing'):
                counts['missing_or_excluded_content'] += 1; continue
            if product.attributes.get('_catalog_duplicate_of_slug'):
                counts['duplicate_alias'] += 1; continue
            if not options['apply']:
                counts['candidates'] += 1; continue
            images = []
            for image in source.media.filter(last_run_id=source.last_run_id, kind='image', role__in=('main','gallery','variant')).order_by('position','pk'):
                try: images.append(verify_photo(image))
                except (ValueError, OSError): counts['unavailable_photos'] += 1
            if not images:
                counts['no_original_photo'] += 1; continue
            for index, image in enumerate(images):
                ProductImage.objects.using('ecommerce').update_or_create(product=product, url=image.stored_url,
                    defaults={'source_media':image,'position':index,'alt_text':product.name})
            attrs = {**product.attributes, '_catalog_price_preview':True}
            Product.objects.using('ecommerce').filter(pk=product.pk).update(status='active', attributes=attrs,
                description=product.description or preferred_description(source), updated_at=timezone.now())
            counts['visible_price_on_request'] += 1
            if sum(counts.values()) % 25 == 0:
                self.stdout.write(json.dumps({'counts':counts,'last_offer_id':last}));self.stdout.flush()
        self.stdout.write(json.dumps({'counts':counts,'last_offer_id':last}))
