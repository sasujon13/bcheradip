"""Private order contribution reporting, not a supplier settlement ledger.

Never infer historical costs from today's mutable catalogue prices. Unknown
expenses are explicitly unresolved, rather than being counted as free stock.
"""
from decimal import Decimal
from .models import SupplierOffer


def capture_costs(lines, delivery):
    rows = []
    for item, variant in lines:
        offer = SupplierOffer.objects.using('ecommerce').filter(imported_product_id=variant.product_id).select_related('supplier').first()
        rows.append({'product_id': variant.product_id, 'quantity': item.quantity,
                     'source': offer.supplier.name if offer else 'Own inventory',
                     'supplier_id': offer.supplier_id if offer else None,
                     'unit_source_cost': str(variant.cost_price) if variant.cost_price is not None else None})
    return {'version': 1, 'items': rows, 'supplier_delivery': delivery.get('supplier_cost')}


def order_contribution(orders):
    zero = Decimal('0')
    totals = dict.fromkeys(('gross', 'refunds', 'source_cost', 'delivery_cost', 'net', 'unresolved_paid_value'), zero)
    groups = {}
    unresolved = 0
    for order in orders.filter(payment_status__in=['paid', 'refunded']).iterator(chunk_size=250):
        refunded = order.status == 'refunded' or order.payment_status == 'refunded'
        refund = order.grand_total if refunded else zero
        totals['gross'] += order.grand_total
        totals['refunds'] += refund
        snap = order.cost_snapshot or {}
        items = snap.get('items') or []
        complete = bool(items) and all(i.get('unit_source_cost') is not None for i in items)
        delivery = snap.get('supplier_delivery')
        complete = complete and delivery is not None
        if not complete:
            unresolved += 1
            totals['unresolved_paid_value'] += order.grand_total - refund
            continue
        source = sum((Decimal(i['unit_source_cost']) * i['quantity'] for i in items), zero)
        delivery = Decimal(str(delivery))
        net = order.grand_total - refund - source - delivery
        totals['source_cost'] += source
        totals['delivery_cost'] += delivery
        totals['net'] += net
        # A mixed-source order is not arbitrarily apportioned into supplier cash
        # receivables. Keep its actual grouping explicit until settlements exist.
        names = sorted(set(i['source'] for i in items))
        key = ' / '.join(names)
        group = groups.setdefault(key, {'source': key, 'orders': 0, 'gross': zero, 'refunds': zero,
                                        'source_cost': zero, 'delivery_cost': zero, 'net': zero})
        group['orders'] += 1
        for field, value in [('gross', order.grand_total), ('refunds', refund), ('source_cost', source), ('delivery_cost', delivery), ('net', net)]:
            group[field] += value
    return {**totals, 'unresolved_orders': unresolved, 'sources': list(groups.values()),
            'basis': 'Order contribution after refunds, source costs and supplier delivery. Not settled cash, net business profit or confirmed supplier receivables.'}
