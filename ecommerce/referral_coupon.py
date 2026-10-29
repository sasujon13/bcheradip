"""Registered-mobile checkout coupons. Never logs credentials."""
import re
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from cheradip.models import Customer, RewardsWallet, WalletOperation
from cheradip.wallet_service import wallet_coins


REFERRAL_PERCENT = Decimal('1')
COINS_PER_TAKA = Decimal('100')


def _digits(value):
    return re.sub(r'\D', '', str(value or ''))


def normalized_mobile(code):
    digits = _digits(code)
    if digits.startswith('880') and len(digits) >= 12:
        digits = '0' + digits[3:]
    elif re.fullmatch(r'1[3-9]\d{8}', digits):
        digits = '0' + digits
    return digits if re.fullmatch(r'01[3-9]\d{8}', digits) else ''


def looks_like_mobile(code):
    return bool(normalized_mobile(code))


def coupon_usernames(code):
    local = normalized_mobile(code)
    if not local:
        return set()
    national = local[1:]
    return {local, national, '880' + national, '+880' + national}


def registered_customer_for_coupon(code):
    names = coupon_usernames(code)
    if not names:
        return None
    matches = list(Customer.objects.filter(username__in=names, is_active=True)[:2])
    if len(matches) == 1:
        return matches[0]
    exact = str(code or '').strip()
    for customer in matches:
        if customer.username == exact:
            return customer
    return None


def same_account(referrer, buyer_id=None, buyer_phone=''):
    if not referrer:
        return False
    if buyer_id and int(buyer_id) == referrer.pk:
        return True
    if buyer_phone:
        other = registered_customer_for_coupon(buyer_phone)
        return bool(other and other.pk == referrer.pk)
    return False


def referral_discount(subtotal):
    amount = (Decimal(str(subtotal)) * REFERRAL_PERCENT / Decimal('100')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return max(Decimal('0.00'), amount)


def taka_to_coins(amount):
    return int((Decimal(str(amount)) * COINS_PER_TAKA).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def hold_key(number):
    return f'commerce:referral-coupon-hold:{number}'


def credit_key(number):
    return f'commerce:referral-coupon:{number}'


def refund_key(number):
    return f'commerce:referral-coupon-refund:{number}'


def _coupon_info(order):
    info = (order.cost_snapshot or {}).get('referral_coupon') or {}
    referrer_id = info.get('customer_id')
    taka = Decimal(str(info.get('taka') or '0'))
    return referrer_id, taka


def hold_referral_coupon(order):
    """Record the 1% immediately as pending; it is not spendable or withdrawable yet."""
    referrer_id, taka = _coupon_info(order)
    if not referrer_id or taka <= 0:
        return None
    coins = taka_to_coins(taka)
    with transaction.atomic(using='default'):
        if WalletOperation.objects.filter(operation_key__in=[credit_key(order.number), refund_key(order.number)]).exists():
            return None
        _, created = WalletOperation.objects.get_or_create(
            operation_key=hold_key(order.number),
            defaults={'customer_id': referrer_id, 'coins': coins, 'reference_taka': taka},
        )
        if not created:
            return None
        rewards, _ = RewardsWallet.objects.select_for_update().get_or_create(customer_id=referrer_id)
        rewards.pending_taka += taka
        rewards.save(update_fields=['pending_taka', 'updated_at'])
    return coins


def credit_referral_coupon(order):
    """Release a held shop referral coupon into spendable and withdrawable balances."""
    referrer_id, taka = _coupon_info(order)
    if not referrer_id or taka <= 0:
        return None
    coins = taka_to_coins(taka)
    with transaction.atomic(using='default'):
        if WalletOperation.objects.filter(operation_key=refund_key(order.number)).exists():
            return None
        _, created = WalletOperation.objects.get_or_create(
            operation_key=credit_key(order.number),
            defaults={'customer_id': referrer_id, 'coins': coins, 'reference_taka': taka},
        )
        if not created:
            return None
        referrer = Customer.objects.select_for_update().get(pk=referrer_id)
        referrer.settings = {**(referrer.settings or {}), 'balance': wallet_coins(referrer) + coins}
        referrer.save(update_fields=['settings'])
        rewards, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=referrer)
        rewards.available_taka += taka
        rewards.lifetime_earned_taka += taka
        hold = WalletOperation.objects.filter(operation_key=hold_key(order.number)).first()
        if hold:
            rewards.pending_taka = max(Decimal('0.00'), rewards.pending_taka - hold.reference_taka)
        rewards.save(update_fields=['available_taka', 'lifetime_earned_taka', 'pending_taka', 'updated_at'])
    return coins


def reverse_referral_coupon(order):
    """Remove a pending hold, or claw back a released credit, once per order."""
    referrer_id, _ = _coupon_info(order)
    if not referrer_id:
        return None
    with transaction.atomic(using='default'):
        credit = WalletOperation.objects.filter(operation_key=credit_key(order.number)).first()
        hold = WalletOperation.objects.filter(operation_key=hold_key(order.number)).first()
        source = credit or hold
        if not source:
            return None
        _, created = WalletOperation.objects.get_or_create(
            operation_key=refund_key(order.number),
            defaults={'customer_id': referrer_id, 'coins': -source.coins, 'reference_taka': source.reference_taka},
        )
        if not created:
            return None
        referrer = Customer.objects.select_for_update().get(pk=referrer_id)
        rewards, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=referrer)
        if credit:
            referrer.settings = {**(referrer.settings or {}), 'balance': max(0, wallet_coins(referrer) - credit.coins)}
            referrer.save(update_fields=['settings'])
            rewards.available_taka = max(Decimal('0.00'), rewards.available_taka - credit.reference_taka)
            rewards.save(update_fields=['available_taka', 'updated_at'])
        else:
            rewards.pending_taka = max(Decimal('0.00'), rewards.pending_taka - hold.reference_taka)
            rewards.save(update_fields=['pending_taka', 'updated_at'])
    return source.coins
