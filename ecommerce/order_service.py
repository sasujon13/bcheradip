"""Shared, locked order/payment operations for API and Django administration."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from cheradip.models import Customer, RewardsWallet, WalletOperation
from cheradip.wallet_service import wallet_coins
from .models import Order, Payment, ProductVariant, InventoryMovement, OrderStatusHistory, CommerceNotification


TRANSITIONS = {
    'pending': {'confirmed', 'processing', 'completed', 'cancelled'},
    'confirmed': {'processing', 'shipped', 'delivered', 'completed', 'cancelled'},
    'processing': {'shipped', 'delivered', 'completed', 'cancelled'},
    'shipped': {'delivered', 'completed', 'returned'},
    'delivered': {'completed', 'returned'},
    'completed': {'returned'},
    'returned': {'refunded'},
    'cancelled': set(), 'refunded': set(),
}


def settle_wallet_order(order_id):
    """Recoverable second leg: never mark paid without a committed main-wallet debit."""
    with transaction.atomic(using='ecommerce'):
        order = Order.objects.using('ecommerce').select_for_update().get(pk=order_id)
        debit = WalletOperation.objects.filter(operation_key=f'commerce:debit:{order.number}').first()
        if not debit or debit.customer_id != order.customer_id or debit.coins != -int(order.grand_total * 100):
            return False
        refunded = WalletOperation.objects.filter(operation_key=f'commerce:refund:{order.number}').exists()
        if refunded:
            order.payments.filter(method='wallet').update(status='refunded')
            order.payment_status = 'refunded'
            order.save(using='ecommerce', update_fields=['payment_status', 'updated_at'])
            return True
        if order.payment_status == 'refunded':
            return True
        Payment.objects.using('ecommerce').filter(order=order, method='wallet', status='pending').update(
            status='confirmed', confirmed_at=timezone.now(), confirmed_by=debit.customer_id,
        )
        order.payment_status = 'paid'
        order.save(using='ecommerce', update_fields=['payment_status', 'updated_at'])
        return True


def refund_wallet(order):
    """Credit once in the authoritative DB before acknowledging the refund elsewhere."""
    if not order.customer_id:
        raise ValueError('Wallet refund requires the purchasing account.')
    with transaction.atomic(using='default'):
        customer = Customer.objects.select_for_update().get(pk=order.customer_id)
        debit = WalletOperation.objects.filter(operation_key=f'commerce:debit:{order.number}').first()
        if not debit or debit.customer_id != customer.pk:
            raise ValueError('This historical payment needs manual reconciliation; no automatic refund was made.')
        _, created = WalletOperation.objects.get_or_create(
            operation_key=f'commerce:refund:{order.number}',
            defaults={'customer': customer, 'coins': -debit.coins, 'reference_taka': debit.reference_taka},
        )
        if created:
            customer.settings = {**(customer.settings or {}), 'balance': wallet_coins(customer) - debit.coins}
            customer.save(update_fields=['settings'])
            rewards, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=customer)
            rewards.available_taka += debit.reference_taka
            rewards.save(update_fields=['available_taka', 'updated_at'])


@transaction.atomic(using='ecommerce')
def change_order(order_id, new_status, actor_id=None, note='', admin_note=None):
    order = Order.objects.using('ecommerce').select_for_update().get(pk=order_id)
    old_status = order.status
    if new_status != old_status and new_status not in TRANSITIONS.get(old_status, set()):
        raise ValueError(f'Cannot change a {old_status} order to {new_status}.')
    wallet = order.payments.filter(method='wallet').exists()
    if new_status == 'completed' and order.payment_status == 'refunded':
        raise ValueError('A refunded payment cannot complete an order.')
    if new_status == 'completed' and wallet:
        if not settle_wallet_order(order.pk):
            raise ValueError('Wallet payment has not been reconciled. Completion is blocked.')
        order.refresh_from_db(using='ecommerce', fields=['payment_status'])
        if order.payment_status == 'refunded':
            raise ValueError('A refunded payment cannot complete an order.')
    if new_status in {'cancelled', 'refunded'} and wallet:
        refund_wallet(order)
        order.payment_status = 'refunded'
        order.payments.filter(method='wallet').update(status='refunded')
    elif new_status == 'completed':
        order.payment_status = 'paid'
        order.payments.filter(status='pending').update(status='confirmed', confirmed_by=actor_id, confirmed_at=timezone.now())
    if new_status != old_status and new_status in {'cancelled', 'returned'}:
        for item in order.items.order_by('variant_id'):
            # Movement is an immutable once-only stock return under the order lock.
            if InventoryMovement.objects.using('ecommerce').filter(
                variant_id=item.variant_id, reference=order.number, reason__in=['cancel', 'return'],
            ).exists():
                continue
            variant = ProductVariant.objects.using('ecommerce').select_for_update().filter(pk=item.variant_id).first()
            if variant:
                variant.stock += item.quantity
                variant.save(using='ecommerce', update_fields=['stock', 'updated_at'])
                InventoryMovement.objects.using('ecommerce').create(
                    variant=variant, quantity=item.quantity, reason='cancel' if new_status == 'cancelled' else 'return',
                    reference=order.number, actor_id=actor_id,
                )
    order.status = new_status
    if admin_note is not None:
        order.admin_note = admin_note
    if new_status == 'confirmed' and not order.confirmed_at:
        order.confirmed_at = timezone.now()
    if new_status in {'shipped', 'delivered', 'completed'} and not order.fulfilled_at:
        order.fulfilled_at = timezone.now()
    order.save(using='ecommerce')
    if old_status != new_status:
        OrderStatusHistory.objects.using('ecommerce').create(order=order, status=new_status, note=note[:500], actor_id=actor_id)
        CommerceNotification.objects.using('ecommerce').create(
            kind='order', title=f'Order {order.number}: {new_status}', message=note,
            link=f'/history?order={order.number}', customer_id=order.customer_id,
        )
    return order


@transaction.atomic(using='ecommerce')
def change_payment(payment_id, new_status, actor_id=None, note=''):
    # Same lock order as checkout/order changes: order before payment.
    payment = Payment.objects.using('ecommerce').get(pk=payment_id)
    order = Order.objects.using('ecommerce').select_for_update().get(pk=payment.order_id)
    payment = Payment.objects.using('ecommerce').select_for_update().get(pk=payment_id)
    allowed = {'pending': {'confirmed', 'failed'}, 'confirmed': {'refunded'}, 'failed': set(), 'refunded': set()}
    if new_status != payment.status and new_status not in allowed.get(payment.status, set()):
        raise ValueError('Invalid payment status transition.')
    if new_status == 'confirmed' and order.status in {'cancelled', 'refunded'}:
        raise ValueError('A cancelled or refunded order cannot receive a payment confirmation.')
    if payment.method == 'wallet' and new_status == 'confirmed':
        if not settle_wallet_order(order.pk):
            raise ValueError('No committed wallet debit exists. Reconcile this order first.')
        order.refresh_from_db(using='ecommerce', fields=['payment_status'])
        if order.payment_status == 'refunded':
            raise ValueError('A refunded payment cannot be confirmed.')
    if payment.method == 'wallet' and new_status == 'refunded':
        refund_wallet(order)
    payment.status = new_status
    payment.note = note[:500]
    if new_status == 'confirmed':
        payment.confirmed_by, payment.confirmed_at = actor_id, timezone.now()
    payment.save(using='ecommerce')
    if new_status == 'refunded':
        order.payment_status = 'refunded'
    elif order.payments.filter(status='confirmed').exists():
        order.payment_status = 'paid'
    else:
        order.payment_status = 'pending' if order.payments.filter(status='pending').exists() else 'failed'
    order.save(using='ecommerce', update_fields=['payment_status', 'updated_at'])
    return payment
