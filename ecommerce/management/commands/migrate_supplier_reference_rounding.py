"""Round generated reference prices and apply their sale discount afterward."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import json

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ecommerce.models import Product, ProductVariant
from ecommerce.pricing import round_reference_price_to_ten, discounted_reference_price
from ecommerce.supplier_service import audit


class Command(BaseCommand):
    help = 'Round generated references to Tk 10, then apply the configured sale discount. Dry run by default.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Persist the reference and discounted sale prices.')

    def handle(self, *args, **options):
        apply = options['apply']
        counts = Counter()
        samples = []
        rows = ProductVariant.objects.using('ecommerce').filter(
            is_active=True,
            product__attributes__manual_supplier_catalogue=True,
            product__supplier_offer__source_product__isnull=False,
            compare_at_price__isnull=False,
        ).order_by('pk').values_list('pk', 'product_id').iterator(chunk_size=200)

        for processed, (variant_id, product_id) in enumerate(rows, 1):
            if processed % 250 == 0:
                self.stdout.write(json.dumps({'processed': processed, 'counts': dict(counts), 'apply': apply}))
                self.stdout.flush()
            with transaction.atomic(using='ecommerce'):
                product = Product.objects.using('ecommerce').select_for_update().get(pk=product_id)
                variant = ProductVariant.objects.using('ecommerce').select_for_update().get(pk=variant_id)
                all_rules = (product.attributes or {}).get('_retail_pricing', {})
                rule = all_rules.get(str(variant_id), {})
                if not isinstance(rule, dict) or rule.get('mode') != 'sale' or rule.get('version', 1) >= 3:
                    counts['not_legacy_generated'] += 1
                    continue
                try:
                    # Only touch a generated value while both stored prices still
                    # match its marker. A staff-edited price is left untouched.
                    if (Decimal(str(rule.get('applied_price', '-1'))) != variant.price or
                            Decimal(str(rule.get('regular_price', '-1'))) != variant.compare_at_price):
                        counts['manual_or_changed_price_preserved'] += 1
                        continue
                    old_reference = variant.compare_at_price
                    old_sale = variant.price
                    new_reference = round_reference_price_to_ten(old_reference)
                    new_sale = discounted_reference_price(new_reference, rule.get('discount_percent', '10'))
                except (InvalidOperation, TypeError, ValueError):
                    counts['invalid_legacy_metadata'] += 1
                    continue

                counts['migrated'] += 1
                if old_reference != new_reference:
                    counts['reference_prices_changed'] += 1
                if old_sale != new_sale:
                    counts['sale_prices_changed'] += 1
                if len(samples) < 10:
                    samples.append({
                        'variant_id': variant_id,
                        'product': product.name,
                        'old_reference': str(old_reference),
                        'new_reference': str(new_reference),
                        'old_sale': str(old_sale),
                        'new_sale': str(new_sale),
                        'discount_percent': rule.get('discount_percent', '10'),
                    })
                if not apply:
                    continue

                variant.compare_at_price = new_reference
                variant.price = new_sale
                variant.save(using='ecommerce', update_fields=['price', 'compare_at_price', 'updated_at'])
                updated_rule = {
                    **rule,
                    'regular_price': str(new_reference),
                    'sale_price': str(new_sale),
                    'applied_price': str(new_sale),
                    'rounding': 'nearest_ten_remainder_4_rounds_up',
                    'version': 3,
                    'updated_at': timezone.now().isoformat(),
                }
                Product.objects.using('ecommerce').filter(pk=product_id).update(
                    attributes={**(product.attributes or {}), '_retail_pricing': {**all_rules, str(variant_id): updated_rule}}
                )
                offer = product.supplier_offer
                audit(
                    'supplier_reference_price_rounding_migrated',
                    supplier=offer.supplier,
                    offer=offer,
                    variant_id=variant_id,
                    old_reference=str(old_reference),
                    new_reference=str(new_reference),
                    old_sale=str(old_sale),
                    new_sale=str(new_sale),
                    previous_rule=rule,
                    rule_version=3,
                )

        self.stdout.write(json.dumps({
            'apply': apply,
            'counts': dict(counts),
            'samples': samples,
            'sale_prices_changed': counts['sale_prices_changed'],
            'staff_edited_prices_preserved': True,
        }, ensure_ascii=False, default=str))
