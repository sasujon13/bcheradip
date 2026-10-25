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


def vendor_shipment_key(product):
    """Stable shipment grouping for products sold by the same supplier vendor."""
    from .models import SupplierOffer
    if product._state.adding:
        # In-memory quote math and unsaved fixture objects have no supplier
        # identity to look up; keep those fees distinct by product.
        return ('product', product.pk if product.pk is not None else id(product))
    origin = SupplierOffer.objects.using('ecommerce').filter(
        imported_product_id=product.pk
    ).values_list('supplier_id', 'vendor_id', 'warehouse_id').first()
    if origin and origin[1] and origin[1] != 'not-provided':
        return ('vendor', *origin)
    # Without a verified vendor identity, keep the fee separate rather than
    # accidentally undercharging unrelated supplier products.
    return ('product', product.pk if product.pk is not None else id(product))


def split_supplier_delivery(lines, dhaka, fallback_charge):
    """Return ordinary lines and one verified supplier charge per vendor shipment.

    Fixed product/vendor fees are charged once per vendor shipment. Weight
    tariffs use the combined weight of selected quantities; products from the
    same vendor still produce one shipment charge.
    """
    groups, ordinary = {}, []
    for variant, quantity in lines:
        if not variant.requires_shipping or not variant.product.supplier_delivery_rates:
            ordinary.append((variant, quantity))
            continue
        rates = validate_rates(variant.product.supplier_delivery_rates)
        key = (('confirmed-shipment', rates['shipment_group']) if rates.get('shipment_group')
               else vendor_shipment_key(variant.product))
        group = groups.setdefault(key, {'products': {}})
        product = group['products'].setdefault(variant.product_id, {
            'rates': rates, 'weight': 0, 'estimated_weight': False,
        })
        product['weight'] += (variant.weight_grams or 0) * quantity
        product['estimated_weight'] = product['estimated_weight'] or not bool(variant.weight_grams)
    shipments = []
    for group in groups.values():
        charges = []
        unknown_weight = any(product['estimated_weight'] for product in group['products'].values())
        if not unknown_weight:
            total_weight=sum(product['weight'] for product in group['products'].values())
            for product in group['products'].values():
                bands=product['rates'].get('dhaka' if dhaka else 'outside', [])
                amount=next((band['charge'] for band in bands if total_weight<=band['up_to_grams']),None)
                if amount is None:
                    raise ValueError('Supplier delivery is not confirmed for this area or parcel weight. Contact support.')
                charges.append(money(amount,'Supplier delivery'))
        shipments.append({'weight_grams': sum(p['weight'] for p in group['products'].values()),
                          'charged': str(money(fallback_charge, 'Fallback delivery') if unknown_weight else max(charges)),
                          'basis': 'fallback_unknown_weight' if unknown_weight else 'supplier_confirmed_vendor_tariff',
                          'estimated_weight': unknown_weight})
    return ordinary, shipments
