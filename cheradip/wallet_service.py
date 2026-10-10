"""Authoritative Cheradip main-wallet and reference-balance operations."""
from decimal import Decimal

from .models import RewardsWallet


COINS_PER_TAKA = Decimal('100')


def wallet_coins(customer):
    settings = customer.settings if isinstance(customer.settings, dict) else {}
    try:
        return max(0, int(settings.get('balance', 0) or 0))
    except (TypeError, ValueError):
        return 0


def deduct_wallet_coins(customer, coins):
    """Deduct coins and consume the withdrawable reference portion first.

    Call this inside ``transaction.atomic()`` while the Customer row is locked.
    Referral commission coins are part of the main balance, while
    ``RewardsWallet.available_taka`` tracks the still-withdrawable part of that
    same value. Reducing both here prevents spending and later withdrawing the
    same referral earnings.
    """
    debit = max(0, int(coins or 0))
    before_coins = wallet_coins(customer)
    if debit > before_coins:
        raise ValueError(f'insufficient:{debit}:{before_coins}')

    remaining_coins = before_coins - debit
    if debit:
        settings = dict(customer.settings) if isinstance(customer.settings, dict) else {}
        settings['balance'] = remaining_coins
        customer.settings = settings
        customer.save(update_fields=['settings'])

    rewards, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=customer)
    debit_taka = (Decimal(debit) / COINS_PER_TAKA).quantize(Decimal('0.01'))
    reference_used_taka = min(rewards.available_taka, debit_taka)
    if reference_used_taka:
        rewards.available_taka -= reference_used_taka
        rewards.save(update_fields=['available_taka', 'updated_at'])

    return {
        'remaining_coins': remaining_coins,
        'remaining_taka': (Decimal(remaining_coins) / COINS_PER_TAKA).quantize(Decimal('0.01')),
        'reference_used_taka': reference_used_taka,
        'reference_balance_taka': rewards.available_taka,
    }
