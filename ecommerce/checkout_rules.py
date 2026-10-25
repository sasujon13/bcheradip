"""Validated, authoritative checkout quotes. No stock or wallet writes here."""
import re
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from .delivery_rates import delivery_zone, weight_range

from django.utils import timezone
from rest_framework import serializers
from .models import Coupon, DeliverySettings, Payment


class AddressSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=2, default='BD')
    division = serializers.CharField(max_length=100, required=False, allow_blank=True)
    district = serializers.CharField(max_length=100, required=False, allow_blank=True)
    thana = serializers.CharField(max_length=100, required=False, allow_blank=True)
    zone = serializers.CharField(max_length=150, required=False, allow_blank=True)
    address = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate(self, data):
        data['country_code'] = data['country_code'].upper()
        # Retain old clients that sent the district as city; new checkout sends district.
        data['district'] = data.get('district') or data.get('city', '')
        return data


def contact_number(value):
    normalized = re.sub(r'[\s().-]', '', value)
    if not re.fullmatch(r'\+?[0-9]{7,15}', normalized):
        raise serializers.ValidationError('Enter a valid contact number (7–15 digits, optional country code).')
    return normalized


class CheckoutInputSerializer(serializers.Serializer):
    cart_token = serializers.CharField(max_length=80)
    customer_name = serializers.CharField(max_length=200)
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=40, validators=[contact_number])
    phone_alternate = serializers.CharField(max_length=40, required=False, allow_blank=True)
    shipping_address = AddressSerializer()
    billing_address = AddressSerializer(required=False)
    payment_method = serializers.ChoiceField(choices=Payment.METHODS, default='cod')
    coupon_code = serializers.CharField(max_length=80, required=False, allow_blank=True, default='')
    customer_note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')
    transaction_id = serializers.CharField(max_length=160, required=False, allow_blank=True, default='')
    quoted_total = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, min_value=0)

    def validate_phone_alternate(self, value):
        return contact_number(value) if value else ''

    def validate_phone(self, value):
        return contact_number(value)

    def validate(self, data):
        if not data['shipping_address'].get('address', '').strip():
            raise serializers.ValidationError({'shipping_address': 'Enter the street/village delivery address.'})
        if data['payment_method'] not in {'cod', 'wallet'} and not data['transaction_id'].strip():
            raise serializers.ValidationError({'transaction_id': 'Provide the payment transaction/reference number for manual verification.'})
        from .phone_display import local_contact
        country=data['shipping_address'].get('country_code','BD')
        data['phone']=local_contact(data['phone'],country)
        data['phone_alternate']=local_contact(data.get('phone_alternate',''),country)
        return data


def quote_totals(subtotal, requires_shipping, address, coupon_code='', lock=False, *, lines=None, payment_method='cod'):
    subtotal = Decimal(str(subtotal))
    policy = DeliverySettings.current()
    if requires_shipping and not address.get('district'):
        raise serializers.ValidationError({'shipping_address': 'Select your delivery district.'})
    if requires_shipping and address.get('country_code', 'BD').upper() != 'BD':
        raise serializers.ValidationError({'shipping_address': 'Physical delivery is currently available within Bangladesh only.'})
    district = re.sub(r'[\s._-]+', '', str(address.get('district', '')).casefold())
    dhaka = district in {'dhaka', 'dhakadistrict', 'ঢাকা', 'ঢাকাজেলা'}
    if not subtotal.is_finite() or subtotal < 0:
        raise serializers.ValidationError('The cart contains an invalid price. Please contact support.')
    lines = list(lines) if lines is not None else None

    def effective(product, field, default, maximum):
        override = getattr(product, field, None) if product is not None else None
        amount = Decimal(str(default if override is None else override))
        if not amount.is_finite() or not 0 <= amount <= maximum:
            raise serializers.ValidationError('Delivery/COD charges are misconfigured. Please contact support.')
        return amount

    delivery_field = 'delivery_dhaka_charge' if dhaka else 'delivery_outside_dhaka_charge'
    default_delivery = policy.dhaka_charge if dhaka else policy.outside_dhaka_charge
    details = {'zone': delivery_zone(address), 'weight_grams': 0, 'estimated_weight': False, 'rates': []}
    if lines is None:
        shipping = effective(None, delivery_field, default_delivery, Decimal('99999999.99')) if requires_shipping else Decimal('0')
    else:
        from .supplier_delivery import split_supplier_delivery
        all_lines = lines
        try:
            lines, supplier_shipments = split_supplier_delivery(
                lines, dhaka, effective(None, delivery_field, default_delivery, Decimal('99999999.99')))
        except ValueError as exc:
            raise serializers.ValidationError({'shipping_address': str(exc)})
        direct = sum((Decimal(s['charged']) for s in supplier_shipments), Decimal('0'))
        details['supplier_shipments'] = supplier_shipments
        # A product-specific fee is charged once per supplier/vendor shipment,
        # regardless of line quantity. When several selected products share a
        # vendor, charge that vendor's highest applicable product fee once.
        fees = {}; product_fee_vendor_keys = set(); normal = []
        for variant, _ in lines:
            if variant.requires_shipping:
                if getattr(variant.product, delivery_field) is not None:
                    from .supplier_delivery import vendor_shipment_key
                    key = vendor_shipment_key(variant.product)
                    product_fee_vendor_keys.add(key)
                    fee = effective(variant.product, delivery_field, default_delivery, Decimal('99999999.99'))
                    fees[key] = max(fees.get(key, Decimal('0')), fee)
        for variant, _ in lines:
            if variant.requires_shipping and getattr(variant.product, delivery_field) is None:
                from .supplier_delivery import vendor_shipment_key
                key = vendor_shipment_key(variant.product)
                if key in product_fee_vendor_keys:
                    fees[key] = max(fees[key], effective(None, delivery_field, default_delivery, Decimal('99999999.99')))
        normal = [(v,q) for v,q in lines if v.requires_shipping and
                  getattr(v.product,delivery_field) is None and
                  (vendor_shipment_key(v.product) not in product_fee_vendor_keys)]
        details['weight_grams'] = sum((v.weight_grams or 0)*q for v,q in lines if v.requires_shipping)
        details['estimated_weight'] = any(not v.weight_grams for v,q in lines if v.requires_shipping)
        product_fee_total = sum(fees.values(), Decimal('0'))
        candidates = []
        if normal:
            if any(not v.weight_grams for v,q in normal):
                # Preserve existing flat fees when a weight is unknown; never
                # silently claim an invented weight is the measured parcel weight.
                candidates.append(effective(None, delivery_field, default_delivery, Decimal('99999999.99')))
                details['fallback'] = 'missing_product_weight'
            else:
                try:
                    rated = weight_range(policy, sum(v.weight_grams*q for v,q in normal), details['zone'])
                except ValueError as exc:
                    if str(exc) != 'This parcel needs a manual courier quote. Contact support before ordering.':
                        raise serializers.ValidationError({'shipping_address': str(exc)})
                    # A known parcel can exceed every configured courier band.
                    # Use the existing area default as a clearly labelled
                    # provisional quote instead of making checkout totals fail.
                    candidates.append(effective(None, delivery_field, default_delivery, Decimal('99999999.99')))
                    details['fallback'] = 'no_courier_rate_for_weight'
                else:
                    candidates += [Decimal(rated['minimum']), Decimal(rated['maximum'])]
                    details['rates'] = rated['rates']
        low, high = (min(candidates), max(candidates)) if candidates else (Decimal('0'),Decimal('0'))
        ordinary_shipping = ((low+high)/2).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        shipping = product_fee_total + ordinary_shipping + direct
        details.update(minimum=str(low + product_fee_total + direct), maximum=str(high + product_fee_total + direct))
        details['product_fee_total'] = str(product_fee_total)
        details['supplier_vendor_fee_total'] = str(direct)
        # Do not present an ordinary courier estimate as a confirmed expense.
        if not any(v.requires_shipping for v,q in lines):
            details['supplier_cost'] = str(direct)
        details['weight_grams'] += sum(s['weight_grams'] for s in supplier_shipments)
        details['estimated_weight'] = details['estimated_weight'] or any(s.get('estimated_weight') for s in supplier_shipments)
        lines = all_lines  # COD applies to every product, not just ordinary parcels.
    if not requires_shipping:
        details['supplier_cost'] = '0.00'
    details['charged'] = str(shipping)
    discount = Decimal('0')
    coupon = None
    code = coupon_code.strip().upper()
    if code:
        query = Coupon.objects.using('ecommerce')
        if lock:
            query = query.select_for_update()
        coupon = query.filter(code__iexact=code, is_active=True).first()
        now = timezone.now()
        if not coupon or (coupon.starts_at and coupon.starts_at > now) or (coupon.ends_at and coupon.ends_at < now) or subtotal < coupon.minimum_order or (coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit):
            raise serializers.ValidationError({'coupon_code': 'This coupon is invalid, expired, exhausted, or its minimum order has not been reached.'})
        if coupon.discount_type == 'percent':
            discount = subtotal * min(Decimal('100'), max(Decimal('0'), coupon.value)) / 100
            if coupon.value == Decimal('10') and lines is not None and sum(
                    (v.price * quantity for v, quantity in lines), Decimal('0')) == subtotal:
                from .pricing import reserved_ten_percent_discount
                # Only owner-configured, unchanged reserve prices get whole-taka
                # per-unit rounding. An ordinary/manual-price line stays at 10%.
                for variant, quantity in lines:
                    reserved_discount = reserved_ten_percent_discount(variant)
                    if reserved_discount is not None:
                        discount += (reserved_discount - variant.price / 10) * quantity
        elif coupon.discount_type == 'fixed':
            discount = min(subtotal, max(Decimal('0'), coupon.value))
        elif coupon.discount_type == 'shipping':
            shipping = Decimal('0')
            details['charged'] = '0.00'; details['free_shipping_coupon'] = True
    discount = discount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    cod = Decimal('0')
    if payment_method == 'cod' and subtotal:
        net_ratio = (subtotal - discount) / subtotal
        if lines is None:
            cod = (subtotal - discount) * effective(None, 'cod_percent', policy.cod_percent, Decimal('100')) / 100
        else:
            cod = sum((v.price * quantity * net_ratio * effective(v.product, 'cod_percent', policy.cod_percent, Decimal('100')) / 100
                       for v, quantity in lines), Decimal('0'))
        cod = cod.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    exact_total = (subtotal - discount + shipping + cod).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    total=exact_total.to_integral_value(rounding=ROUND_CEILING).quantize(Decimal('.01'))
    adjustment=total-exact_total
    details['rounding_adjustment']=str(adjustment)
    if total > Decimal('999999999999.99'):
        raise serializers.ValidationError('The order total exceeds the supported amount. Please split the order.')
    return {'subtotal': subtotal, 'shipping_total': shipping, 'discount_total': discount,
            'cod_total': cod, 'grand_total': total, 'rounding_adjustment':adjustment,'coupon_code': code, 'delivery_details': details}, coupon
