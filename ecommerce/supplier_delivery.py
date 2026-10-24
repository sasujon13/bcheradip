"""Explicit, verified supplier shipping overrides; never inferred from retail prices."""
from .pricing import money


def validate_rates(value):
    if not isinstance(value, dict) or set(value) - {'dhaka', 'outside', 'shipment_group'}:
        raise ValueError('Supplier delivery needs dhaka/outside weight bands and an optional confirmed shipment_group.')
    if not value:
        return value
    if not any(value.get(zone) for zone in ('dhaka', 'outside')):
        raise ValueError('Supply a verified delivery weight band.')
    if 'shipment_group' in value and (not isinstance(value['shipment_group'], str) or not 1 <= len(value['shipment_group']) <= 160):
        raise ValueError('Use a non-empty shipment group of at most 160 characters.')
    result = {k: value[k] for k in ('shipment_group',) if k in value}
    for zone in ('dhaka', 'outside'):
        if zone not in value:
            continue
        bands = value[zone]
        if not isinstance(bands, list) or not 1 <= len(bands) <= 30:
            raise ValueError('Use 1–30 supplier weight bands per area.')
        previous = 0
        result[zone] = []
        for band in bands:
            grams = band.get('up_to_grams') if isinstance(band, dict) else None
            if isinstance(grams, bool) or not isinstance(grams, int) or not previous < grams <= 1000000:
                raise ValueError('Supplier weight bands must increase and use positive integer grams.')
            result[zone].append({'up_to_grams': grams, 'charge': str(money(band.get('charge'), 'Supplier delivery'))})
            previous = grams
    return result


def split_supplier_delivery(lines, dhaka):
    """Return ordinary lines, verified shipment charges and their customer-visible breakdown."""
    groups, ordinary = {}, []
    for variant, quantity in lines:
        if not variant.requires_shipping or not variant.product.supplier_delivery_rates:
            ordinary.append((variant, quantity))
            continue
        rates = validate_rates(variant.product.supplier_delivery_rates)
        key = rates.get('shipment_group') or f'product:{variant.product_id}'
        # Identical human group labels cannot combine different supplier/vendor origins.
        from .models import SupplierOffer
        origin=SupplierOffer.objects.using('ecommerce').filter(imported_product_id=variant.product_id).values_list('supplier_id','vendor_id','warehouse_id').first()
        if origin: key=(origin,key)
        group = groups.setdefault(key, {'rates': rates, 'weight': 0})
        if group['rates'] != rates:
            raise ValueError('Consolidated supplier delivery schedules conflict. Ask staff to verify the shipment.')
        if not variant.weight_grams:
            raise ValueError('A supplier shipping quote requires the actual product weight. Contact support.')
        group['weight'] += variant.weight_grams * quantity
    shipments = []
    for group in groups.values():
        amount = next((b['charge'] for b in group['rates'].get('dhaka' if dhaka else 'outside', [])
                       if group['weight'] <= b['up_to_grams']), None)
        if amount is None:
            raise ValueError('Supplier delivery is not confirmed for this area or parcel weight. Contact support.')
        shipments.append({'weight_grams': group['weight'], 'charged': amount, 'basis': 'supplier_confirmed_tariff'})
    return ordinary, shipments
