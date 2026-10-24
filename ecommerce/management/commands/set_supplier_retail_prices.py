"""Explicit, idempotent owner pricing update; never mutates accepted orders."""
from collections import Counter
from decimal import Decimal
import json
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from ecommerce.models import Product, ProductVariant
from ecommerce.pricing import retail_prices
from ecommerce.supplier_service import audit


class Command(BaseCommand):
    help = 'Round supplier listing prices and optionally reserve a future 10% discount. Dry run by default.'

    def add_arguments(self, parser):
        parser.add_argument('--mode', choices=('round', 'reserve', 'sale'), default='sale')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--only-unconfigured', action='store_true', help='Background follow-through: never overwrite a later staff price or an already configured rule.')

    def handle(self, *args, **options):
        counts = Counter()
        rows = ProductVariant.objects.using('ecommerce').filter(
            product__attributes__manual_supplier_catalogue=True, product__supplier_offer__source_product__isnull=False,
            price__gt=0).values_list('pk', 'product_id')
        for processed,(pk, product_id) in enumerate(rows.iterator(),1):
            if processed % 250 == 0:
                self.stdout.write(json.dumps({'processed':processed,'counts':counts,'mode':options['mode']}))
                self.stdout.flush()
            with transaction.atomic(using='ecommerce'):
                # Match the publisher/checkout lock order: parent before variant.
                product = Product.objects.using('ecommerce').select_for_update().get(pk=product_id)
                variant = ProductVariant.objects.using('ecommerce').select_for_update().get(pk=pk)
                previous = (product.attributes or {}).get('_retail_pricing', {}).get(str(pk), {})
                if options['only_unconfigured'] and previous and (
                    previous.get('mode') == options['mode'] or
                    (previous.get('applied_price') is not None and variant.price != Decimal(previous['applied_price']))):
                    counts['configured_or_staff_price_preserved'] += 1
                    continue
                # Repeated deploys/runs reuse the original base only when the last
                # generated price still matches. An intervening staff edit wins.
                baseline = previous.get('base_price') if previous.get('applied_price') is not None and variant.price == Decimal(previous['applied_price']) else str(variant.price)
                from ecommerce.models import DeliverySettings
                pair = retail_prices(baseline,DeliverySettings.current().pricing_rules)
                price = Decimal(pair['regular_price'] if options['mode'] == 'reserve' else pair['sale_price'])
                compare = Decimal(pair['regular_price']) if options['mode'] == 'sale' else None
                if price == variant.price and compare == variant.compare_at_price and previous.get('mode') == options['mode']:
                    counts['unchanged'] += 1
                    continue
                counts['changed'] += 1
                if not options['apply']:
                    continue
                old_price = variant.price
                variant.price, variant.compare_at_price = price, compare
                variant.save(using='ecommerce', update_fields=['price', 'compare_at_price', 'updated_at'])
                pair.update(mode=options['mode'], applied_price=str(variant.price), updated_at=timezone.now().isoformat())
                all_rules = {**(product.attributes or {}).get('_retail_pricing', {}), str(pk): pair}
                type(product).objects.using('ecommerce').filter(pk=product.pk).update(
                    attributes={**product.attributes, '_retail_pricing': all_rules})
                audit('owner_supplier_retail_price_updated', supplier=product.supplier_offer.supplier,
                      offer=product.supplier_offer, variant_id=pk, old_price=str(old_price),
                      new_price=str(price), mode=options['mode'], accepted_orders_unchanged=True)
        self.stdout.write(json.dumps({'apply': options['apply'], 'mode': options['mode'], 'counts': counts,
                                     'accepted_orders_unchanged': True}))
