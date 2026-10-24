"""Owner-approved confirmed orders for source-labelled stock without quantity.

Quantity stays unknown, never an invented unlimited inventory count. Historical
confirmation holds retain their recorded rules; new orders use normal payments.
"""
from django.utils import timezone

MARKER = '_stock_confirmation_required'
NOTICE = ('Supplier reports this item in stock but does not specify a quantity. '
          'Orders are confirmed upon placement, subject to supplier fulfilment. '
          'If the supplier cannot deliver, we will cancel the affected order and refund any payment due.')


def quantity_unspecified(variant):
    attrs = variant.product.attributes or {}
    return bool(attrs.get('manual_supplier_catalogue') and attrs.get(MARKER) and variant.allow_backorder)


def required(variant):
    # Compatibility field for older API clients. Unknown quantity no longer
    # creates a staff-confirmation/payment hold on newly placed orders.
    return False


def checkout_policy(lines, payment_method):
    lines=list(lines)
    ids = sorted({variant.product_id for variant, _ in lines if quantity_unspecified(variant)})
    # A quantity-free supplier line must not bypass a separate standard/pilot
    # product's administrative approval merely by being put in the same cart.
    automatic=bool(ids) and all((v.product.attributes or {}).get('manual_supplier_catalogue') for v,_ in lines)
    notice=NOTICE if automatic else ('Supplier quantity is not specified; no separate quantity-confirmation hold applies. '
        'Other items retain their usual order approval rules. Fulfilment is subject to supplier availability.') if ids else ''
    return {'required':False,'quantity_unspecified':bool(ids),'auto_confirmed':automatic,
            'policy':'owner_confirm_unspecified_quantity_v1','product_ids':ids,'notice':notice}


def pending(order):
    record = (order.cost_snapshot or {}).get('stock_confirmation') or {}
    return bool(order.status not in {'cancelled','returned','refunded'} and
                record.get('required') and not record.get('confirmed_at'))


def confirm(order, actor_id):
    """An explicit staff order transition records per-order fulfilment approval."""
    if not pending(order):
        return
    from cheradip.models import Customer
    if not actor_id or not Customer.objects.filter(pk=actor_id,is_active=True,is_staff=True).exists():
        raise ValueError('A staff member must confirm this supplier stock request before fulfilment or payment.')
    record = dict(order.cost_snapshot['stock_confirmation'])
    record.update(confirmed_at=timezone.now().isoformat(),confirmed_by=actor_id)
    order.cost_snapshot = {**order.cost_snapshot,'stock_confirmation':record}
