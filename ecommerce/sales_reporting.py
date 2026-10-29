"""Sales research aggregates for commerce-manage Reports → Sales.

Line revenue and checkout snapshot source costs are attributed to SKUs and
suppliers for research. This is not a settlement ledger, not net business
profit, and not confirmed supplier receivables. Delivery stays on the order
and is never apportioned across mixed-source lines. Unknown snapshot costs
stay n/a — never inferred from today's catalogue prices.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Order, OrderItem, Product, Supplier, SupplierOffer

DHAKA = ZoneInfo('Asia/Dhaka')
ZERO = Decimal('0')
TWOPLACES = Decimal('0.01')
PAID_STATUSES = ('paid', 'refunded')
OWN = 0
BATCH = 200
BASIS = (
    'Product sales are paid line totals after full-order refunds. Product profit '
    'subtracts historical snapshot source costs only. Supplier delivery, COD, '
    'discounts and ads are not allocated to SKUs. Missing snapshot costs stay n/a, '
    'never current catalogue prices. Not settled cash or net business profit.'
)


def money(value):
    if value is None:
        return None
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def parse_day(raw):
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationError('Dates must use YYYY-MM-DD.')


def parse_range(params):
    all_time = str(params.get('all') or '').lower() in ('1', 'true', 'yes')
    raw_from = (params.get('from') or '').strip()
    raw_to = (params.get('to') or '').strip()
    today = timezone.now().astimezone(DHAKA).date()
    if all_time:
        return None, None, True, None, None
    if raw_from or raw_to:
        start = parse_day(raw_from) if raw_from else parse_day(raw_to)
        end = parse_day(raw_to) if raw_to else today
    else:
        start = today - timedelta(days=89)
        end = today
    if start > end:
        raise ValidationError('The start date must be on or before the end date.')
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=DHAKA)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=DHAKA)
    return start_dt, end_dt, False, start, end


def _supplier_id(raw):
    value = (raw or '').strip()
    if not value:
        return None
    try:
        selected = int(value)
    except (TypeError, ValueError):
        raise ValidationError('Select a supplier by id.')
    if not Supplier.objects.using('ecommerce').filter(pk=selected).exists():
        raise ValidationError('Unknown supplier.')
    return selected


def _iter_orders(qs):
    last_pk = 0
    while True:
        batch = list(qs.filter(pk__gt=last_pk).order_by('pk').prefetch_related(
            Prefetch('items', queryset=OrderItem.objects.using('ecommerce')))[:BATCH])
        if not batch:
            break
        yield from batch
        last_pk = batch[-1].pk


def _match_snapshot(item, remaining):
    for index, snap in enumerate(remaining):
        if snap.get('product_id') == item.product_id and snap.get('quantity') == item.quantity:
            return remaining.pop(index)
    for index, snap in enumerate(remaining):
        if snap.get('product_id') == item.product_id:
            return remaining.pop(index)
    return None


def _unit_cost(snap):
    if not snap or snap.get('unit_source_cost') is None:
        return None
    return Decimal(str(snap['unit_source_cost']))


def _bucket():
    return {
        'sales': ZERO, 'refunds': ZERO, 'units': 0, 'refunded_units': 0,
        'orders': set(), 'net_orders': set(), 'cost': ZERO, 'missing_cost_units': 0,
        'last_sold': None, 'name': '', 'sku': '', 'product_id': None, 'sku_orders': defaultdict(set),
    }


def _touch(bucket, when):
    if when and (bucket['last_sold'] is None or when > bucket['last_sold']):
        bucket['last_sold'] = when


def _add_line(bucket, *, net, refund, units, refunded_units, cost, order_id, refunded, when, sku=None):
    bucket['sales'] += net
    bucket['refunds'] += refund
    bucket['units'] += units
    bucket['refunded_units'] += refunded_units
    bucket['orders'].add(order_id)
    if not refunded:
        bucket['net_orders'].add(order_id)
    if cost is not None:
        bucket['cost'] += cost
    else:
        bucket['missing_cost_units'] += units + refunded_units
    _touch(bucket, when)
    if sku:
        bucket['sku_orders'][sku].add(order_id)


def _profit(bucket):
    if bucket['missing_cost_units']:
        return None
    if bucket['units'] == 0 and bucket['refunded_units'] == 0:
        return ZERO
    return money(bucket['sales'] - bucket['cost'])


def _margin(profit, sales):
    if profit is None or sales <= 0:
        return None
    return money(profit * 100 / sales)


def _iso(value):
    return value.isoformat() if value else None


def _row_profit_fields(bucket):
    profit = _profit(bucket)
    units = bucket['units']
    return {
        'sales': money(bucket['sales']),
        'refunds': money(bucket['refunds']),
        'units': units,
        'refunded_units': bucket['refunded_units'],
        'orders': len(bucket['net_orders']),
        'order_count': len(bucket['net_orders']),
        'profit': profit,
        'profit_per_unit': money(profit / units) if profit is not None and units else None,
        'margin_percent': _margin(profit, bucket['sales']),
        'cost_unknown_units': bucket['missing_cost_units'],
        'last_sold': _iso(bucket['last_sold']),
    }


def build_sales_report(params):
    selected = _supplier_id(params.get('supplier'))
    start_dt, end_dt, all_time, start, end = parse_range(params)
    orders = Order.objects.using('ecommerce').filter(payment_status__in=PAID_STATUSES)
    if start_dt:
        orders = orders.filter(created_at__gte=start_dt)
    if end_dt:
        orders = orders.filter(created_at__lt=end_dt)

    suppliers = list(Supplier.objects.using('ecommerce').order_by('name').values('id', 'name', 'enabled'))
    names = {row['id']: row['name'] for row in suppliers}
    names[OWN] = 'Own inventory'
    offers = dict(SupplierOffer.objects.using('ecommerce').filter(
        imported_product_id__isnull=False).values_list('imported_product_id', 'supplier_id'))

    supplier_rows = defaultdict(_bucket)
    sku_rows = defaultdict(_bucket)
    series = defaultdict(_bucket)
    range_days = (end - start).days + 1 if start and end else 0
    weekly = all_time or range_days > 90
    sold_product_ids = set()
    delivery_cost = ZERO
    unresolved_orders = 0
    unresolved_paid_value = ZERO
    returned_orders = 0
    order_paid_value = ZERO
    order_ids = set()

    for order in _iter_orders(orders):
        refunded = order.status == 'refunded' or order.payment_status == 'refunded'
        returned = order.status == 'returned'
        snap = order.cost_snapshot or {}
        remaining = list(snap.get('items') or [])
        delivery = snap.get('supplier_delivery')
        complete = bool(remaining) and all(row.get('unit_source_cost') is not None for row in remaining)
        complete = complete and delivery is not None
        refund_amount = order.grand_total if refunded else ZERO
        local = timezone.localtime(order.created_at, DHAKA)
        if weekly:
            iso = local.isocalendar()
            period = f'{iso.year}-W{iso.week:02d}'
        else:
            period = local.date().isoformat()
        items = list(order.items.all())
        used = False
        for item in items:
            snap_item = _match_snapshot(item, remaining)
            supplier_id = snap_item.get('supplier_id') if snap_item else None
            if supplier_id is None:
                supplier_id = offers.get(item.product_id)
            supplier_key = supplier_id if supplier_id is not None else OWN
            if selected is not None and supplier_key != selected:
                continue
            used = True
            sold_product_ids.add(item.product_id)
            unit_cost = _unit_cost(snap_item)
            qty = int(item.quantity)
            line = Decimal(item.line_total)
            net = ZERO if refunded else line
            refund = line if refunded else ZERO
            units = 0 if refunded else qty
            refunded_units = qty if refunded else 0
            if refunded:
                cost = ZERO
            elif unit_cost is None:
                cost = None
            else:
                cost = unit_cost * qty
            sku_key = item.sku or f'product-{item.product_id}'
            sku = sku_rows[sku_key]
            sku['name'] = item.product_name
            sku['sku'] = item.sku
            sku['product_id'] = item.product_id
            _add_line(sku, net=net, refund=refund, units=units, refunded_units=refunded_units,
                      cost=cost, order_id=order.pk, refunded=refunded, when=order.created_at, sku=sku_key)
            _add_line(supplier_rows[supplier_key], net=net, refund=refund, units=units,
                      refunded_units=refunded_units, cost=cost, order_id=order.pk, refunded=refunded,
                      when=order.created_at, sku=sku_key)
            supplier_rows[supplier_key]['name'] = names.get(supplier_key, 'Own inventory')
            _add_line(series[period], net=net, refund=refund, units=units, refunded_units=refunded_units,
                      cost=cost, order_id=order.pk, refunded=refunded, when=order.created_at)
        if not used:
            continue
        order_ids.add(order.pk)
        order_paid_value += order.grand_total - refund_amount
        if returned:
            returned_orders += 1
        if not complete:
            unresolved_orders += 1
            unresolved_paid_value += order.grand_total - refund_amount
        elif selected is None and delivery is not None:
            delivery_cost += Decimal(str(delivery))

    totals_bucket = _bucket()
    totals_bucket['sales'] = sum((sku['sales'] for sku in sku_rows.values()), ZERO)
    totals_bucket['refunds'] = sum((sku['refunds'] for sku in sku_rows.values()), ZERO)
    totals_bucket['units'] = sum(sku['units'] for sku in sku_rows.values())
    totals_bucket['refunded_units'] = sum(sku['refunded_units'] for sku in sku_rows.values())
    totals_bucket['orders'] = set().union(*(sku['orders'] for sku in sku_rows.values())) if sku_rows else set()
    totals_bucket['net_orders'] = set().union(*(sku['net_orders'] for sku in sku_rows.values())) if sku_rows else set()
    totals_bucket['cost'] = sum((sku['cost'] for sku in sku_rows.values() if not sku['missing_cost_units']), ZERO)
    totals_bucket['missing_cost_units'] = sum(sku['missing_cost_units'] for sku in sku_rows.values())
    if any(sku['missing_cost_units'] for sku in sku_rows.values()):
        totals_bucket['missing_cost_units'] = max(1, totals_bucket['missing_cost_units'])
    for sku in sku_rows.values():
        _touch(totals_bucket, sku['last_sold'])

    ranked_skus = sorted(sku_rows.values(), key=lambda row: (row['sales'], row['units']), reverse=True)
    top10_sales = sum((row['sales'] for row in ranked_skus[:10]), ZERO)
    concentration = money(top10_sales * 100 / totals_bucket['sales']) if totals_bucket['sales'] > 0 else None
    top_product = ranked_skus[0]['name'] if ranked_skus else None
    net_orders = len(totals_bucket['net_orders'])
    aov = money(totals_bucket['sales'] / net_orders) if net_orders else None
    units_per_order = money(Decimal(totals_bucket['units']) / net_orders) if net_orders else None
    total_profit = _profit(totals_bucket)

    if selected is None:
        rows = []
        for supplier in suppliers:
            bucket = supplier_rows.get(supplier['id']) or _bucket()
            sku_count = len(bucket['sku_orders'])
            repeat = sum(1 for orders in bucket['sku_orders'].values() if len(orders) >= 2)
            rows.append({
                'supplier_id': supplier['id'], 'supplier_name': supplier['name'], 'enabled': supplier['enabled'],
                'skus_sold': sku_count, 'repeat_skus': repeat,
                'reorder_rate': money(Decimal(repeat * 100) / sku_count) if sku_count else None,
                **_row_profit_fields(bucket),
            })
        if OWN in supplier_rows:
            bucket = supplier_rows[OWN]
            sku_count = len(bucket['sku_orders'])
            repeat = sum(1 for orders in bucket['sku_orders'].values() if len(orders) >= 2)
            rows.append({
                'supplier_id': None, 'supplier_name': 'Own inventory', 'enabled': None,
                'skus_sold': sku_count, 'repeat_skus': repeat,
                'reorder_rate': money(Decimal(repeat * 100) / sku_count) if sku_count else None,
                **_row_profit_fields(bucket),
            })
        rows.sort(key=lambda row: Decimal(row['sales'] or 0), reverse=True)
        view = 'suppliers'
        ranking = [{
            'label': row['supplier_name'], 'sales': row['sales'], 'profit': row['profit'], 'units': row['units'],
        } for row in rows[:12] if Decimal(row['sales'] or 0) > 0 or row['units'] or row['refunded_units']]
    else:
        rows = []
        for bucket in sku_rows.values():
            rows.append({
                'product_id': bucket['product_id'], 'product_name': bucket['name'], 'sku': bucket['sku'],
                **_row_profit_fields(bucket),
            })
        rows.sort(key=lambda row: Decimal(row['sales'] or 0), reverse=True)
        view = 'products'
        ranking = [{
            'label': row['product_name'] or row['sku'], 'sales': row['sales'], 'profit': row['profit'],
            'units': row['units'],
        } for row in rows[:12]]

    repeat_winners = [{
        'product_name': row['name'], 'sku': row['sku'], 'orders': len(row['net_orders']),
        'units': row['units'], 'sales': money(row['sales']),
    } for row in sorted(
        (sku for sku in sku_rows.values() if len(sku['net_orders']) >= 2),
        key=lambda sku: sku['units'], reverse=True)[:10]]
    slow_movers = [{
        'product_name': row['name'], 'sku': row['sku'], 'orders': len(row['net_orders']),
        'units': row['units'], 'sales': money(row['sales']), 'last_sold': _iso(row['last_sold']),
    } for row in sorted(
        (sku for sku in sku_rows.values() if len(sku['net_orders']) == 1),
        key=lambda sku: sku['last_sold'] or timezone.now())[:20]]
    unsold = []
    if selected is not None:
        unsold = list(Product.objects.using('ecommerce').filter(
            status='active', supplier_offer__supplier_id=selected).exclude(
            pk__in=sold_product_ids).order_by('name').values('id', 'name', 'slug')[:20])
    loss_makers = [{
        'label': row.get('product_name') or row.get('supplier_name'),
        'sku': row.get('sku'), 'profit': row['profit'], 'sales': row['sales'],
    } for row in rows if row['profit'] is not None and Decimal(row['profit']) < 0]

    series_rows = [{
        'period': key, 'sales': money(bucket['sales']), 'profit': _profit(bucket), 'units': bucket['units'],
        'orders': len(bucket['net_orders']),
    } for key, bucket in sorted(series.items())]

    return {
        'view': view,
        'selected_supplier': selected,
        'timezone': 'Asia/Dhaka',
        'all_time': all_time,
        'date_from': start.isoformat() if start else None,
        'date_to': end.isoformat() if end else None,
        'suppliers': suppliers,
        'rows': rows,
        'series': series_rows,
        'ranking': ranking,
        'totals': {
            **_row_profit_fields(totals_bucket),
            'skus_sold': len(sku_rows),
            'repeat_skus': sum(1 for sku in sku_rows.values() if len(sku['net_orders']) >= 2),
            'aov': aov,
            'units_per_order': units_per_order,
            'concentration_top10': concentration,
            'top_product': top_product,
            'returned_orders': returned_orders,
            'unresolved_orders': unresolved_orders,
            'unresolved_paid_value': money(unresolved_paid_value),
            'delivery_cost': money(delivery_cost) if selected is None else None,
            'order_paid_value': money(order_paid_value) if selected is None else None,
            'paid_orders': len(order_ids),
        },
        'extras': {
            'repeat_winners': repeat_winners,
            'slow_movers': slow_movers,
            'unsold_hosted': list(unsold),
            'loss_makers': loss_makers,
        },
        'basis': BASIS,
        'definitions': {
            'sales': 'Paid line totals after full-order refunds.',
            'profit': 'Net line sales minus snapshot source cost when every unit has a captured cost.',
            'repeat_skus': 'SKUs sold in two or more distinct non-refunded orders in this range.',
        },
    }
