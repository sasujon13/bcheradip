"""Single source of truth for package state, renewal, and question entitlement."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .membership import add_months, discounted_price, refresh_membership
from .models import Customer, PackagePlan, PackageSubscription, ReferralCommission


ACADEMIC_PREFIXES = ("BB'", "CB'", "ChB'", "DB'", "DiB'", "JB'", "MB'", "RB'", "SB'", "MSB'")
WARNING_INTERVAL = timedelta(hours=3)
RETRY_INTERVAL = timedelta(days=1)
GRACE_PERIOD = timedelta(days=7)


def _wallet(customer):
    settings = customer.settings if isinstance(customer.settings, dict) else {}
    try:
        return int(settings.get('balance', 0) or 0)
    except (TypeError, ValueError):
        return 0


def _set_wallet(customer, amount):
    settings = dict(customer.settings) if isinstance(customer.settings, dict) else {}
    settings['balance'] = max(0, int(amount))
    customer.settings = settings
    customer.save(update_fields=['settings'])


def _taka_to_coins(amount):
    return int((Decimal(amount) * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _credit_referrer(subscription):
    """Credit referral once; RV is a percentage and one Taka equals 100 coins."""
    customer = subscription.customer
    if not customer.referred_by_id or subscription.payable_amount <= 0:
        return None
    if ReferralCommission.objects.filter(subscription=subscription).exists():
        return None
    referrer = Customer.objects.select_for_update().get(pk=customer.referred_by_id)
    progress = refresh_membership(referrer)
    rv = int(progress.reference_value_percent or 0)
    if rv <= 0:
        return None
    commission_taka = Decimal(subscription.payable_amount) * Decimal(rv) / Decimal('100')
    coins = _taka_to_coins(commission_taka)
    if coins <= 0:
        return None
    row = ReferralCommission.objects.create(
        referrer=referrer, referred_customer=customer, subscription=subscription,
        gross_amount=subscription.payable_amount,
        reference_value_percent=rv, commission_coins=coins,
    )
    _set_wallet(referrer, _wallet(referrer) + coins)
    return row


def current_subscription(customer, now=None, process_renewal=True):
    now = now or timezone.now()
    row = PackageSubscription.objects.filter(
        customer=customer, status__in=['active', 'grace'], starts_at__lte=now,
    ).select_related('plan').order_by('-starts_at', '-id').first()
    if row and process_renewal:
        row = process_subscription_renewal(row, now)
    if not row:
        return None
    if row.status == 'active' and (
        row.ends_at is None or row.ends_at > now or
        (row.plan.price <= 0 and row.ends_at + GRACE_PERIOD >= now)
    ):
        return row
    if row.status == 'grace' and row.grace_ends_at and row.grace_ends_at >= now:
        return row
    return None


@transaction.atomic
def process_subscription_renewal(subscription, now=None):
    """Lazily renew at most once per day; safe to call on every active request."""
    now = now or timezone.now()
    subscription = PackageSubscription.objects.select_for_update().select_related('customer', 'plan').get(pk=subscription.pk)
    successor = PackageSubscription.objects.filter(
        customer=subscription.customer,
        payment_reference=f'auto-renewal:{subscription.id}',
    ).select_related('plan').order_by('-id').first()
    if successor:
        return successor
    if subscription.status not in {'active', 'grace'}:
        return subscription
    if subscription.status == 'grace' and subscription.grace_ends_at and now > subscription.grace_ends_at:
        subscription.status = 'cancelled'
        subscription.renewal_failure_reason = subscription.renewal_failure_reason or 'Wallet charge failed during the 7-day grace period.'
        subscription.save(update_fields=['status', 'renewal_failure_reason', 'updated_at'])
        return subscription
    due = subscription.next_renewal_at or subscription.ends_at
    if subscription.plan.price <= 0:
        free_access_until = subscription.ends_at + GRACE_PERIOD if subscription.ends_at else None
        if free_access_until and free_access_until < now:
            subscription.status = 'expired'
            subscription.save(update_fields=['status', 'updated_at'])
        return subscription
    if not subscription.auto_renew or not due or due > now:
        return subscription
    if subscription.last_renewal_attempt_at and now - subscription.last_renewal_attempt_at < RETRY_INTERVAL:
        return subscription
    progress = refresh_membership(subscription.customer, now)
    charge = discounted_price(subscription.plan.price, progress.discount_percent)
    charge_coins = _taka_to_coins(charge)
    balance = _wallet(subscription.customer)
    subscription.last_renewal_attempt_at = now
    if balance >= charge_coins:
        _set_wallet(subscription.customer, balance - charge_coins)
        subscription.status = 'expired'
        subscription.auto_renew = False
        subscription.save(update_fields=['status', 'auto_renew', 'last_renewal_attempt_at', 'updated_at'])
        renewal_end = add_months(now, subscription.plan.duration_months)
        successor = PackageSubscription.objects.create(
            customer=subscription.customer, plan=subscription.plan, status='active',
            plan_price=subscription.plan.price, badge_discount_percent=progress.discount_percent,
            payable_amount=charge, payment_reference=f'auto-renewal:{subscription.id}',
            starts_at=now, ends_at=renewal_end, next_renewal_at=renewal_end, auto_renew=True,
        )
        _credit_referrer(successor)
        return successor
    else:
        subscription.status = 'grace'
        subscription.renewal_failed_attempts += 1
        subscription.grace_started_at = subscription.grace_started_at or now
        subscription.grace_ends_at = subscription.grace_ends_at or (subscription.grace_started_at + GRACE_PERIOD)
        subscription.renewal_failure_reason = 'Insufficient wallet balance.'
    subscription.save()
    return subscription


def warning_payload(subscription, now=None, mark_shown=False):
    now = now or timezone.now()
    if not subscription or subscription.status != 'grace' or not subscription.grace_ends_at:
        return None
    if subscription.last_warning_at and now - subscription.last_warning_at < WARNING_INTERVAL:
        return None
    seconds = max(0, int((subscription.grace_ends_at - now).total_seconds()))
    days = max(1, (seconds + 86399) // 86400)
    last_day = days <= 1
    message = ('Today is the last day to recharge. Your package will be cancelled when the grace period ends.'
               if last_day else f'Package renewal payment failed. Please recharge within {days} days to keep your package active.')
    if mark_shown:
        subscription.last_warning_at = now
        subscription.save(update_fields=['last_warning_at', 'updated_at'])
    return {'message': message, 'lastDay': last_day, 'daysRemaining': days}


def activate_plan(customer, plan, payment_reference=''):
    """Apply same/downgrade/upgrade rules while retaining every history row."""
    now = timezone.now()
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        current = current_subscription(customer, now)
        progress = refresh_membership(customer, now)
        if current and current.plan_id == plan.id:
            return current, _wallet(customer), False, (
                f'Already activated. Renewal will be charged after the current activation period ends on '
                f'{current.ends_at.date().isoformat() if current.ends_at else "the renewal date"}.'
            )
        is_upgrade = bool(current and plan.sort_order > current.plan.sort_order)
        # Badge discounts apply to the next renewal, not to a fresh activation.
        payable = Decimal(plan.price) if (not current or is_upgrade) else Decimal('0')
        payable_coins = _taka_to_coins(payable)
        balance = _wallet(customer)
        if payable_coins > balance:
            raise ValueError(f'insufficient:{payable}:{payable_coins}:{balance}')
        if payable_coins:
            _set_wallet(customer, balance - payable_coins)
            balance -= payable_coins
        if current:
            current.status = 'superseded'
            current.auto_renew = False
            current.superseded_at = now
            current.save(update_fields=['status', 'auto_renew', 'superseded_at', 'updated_at'])
        ends = add_months(now, plan.duration_months)
        row = PackageSubscription.objects.create(
            customer=customer, plan=plan, status='active', plan_price=plan.price,
            badge_discount_percent=progress.discount_percent, payable_amount=payable,
            payment_reference=str(payment_reference or '')[:80], starts_at=now, ends_at=ends,
            next_renewal_at=ends, auto_renew=plan.price > 0,
        )
        _credit_referrer(row)
        refresh_membership(customer, now)
        kind = 'upgraded' if is_upgrade else ('changed without charge' if current else 'activated')
        return row, balance, True, f'Package {kind} successfully.'


def subscription_payload(row, now=None, mark_warning=False):
    if not row:
        return None
    access_ends = row.grace_ends_at or row.ends_at
    if row.plan.price <= 0 and row.ends_at:
        access_ends = row.ends_at + GRACE_PERIOD
    return {
        'id': row.id, 'planCode': row.plan.code, 'planName': row.plan.name,
        'track': row.plan.track, 'status': row.status, 'autoRenew': row.auto_renew,
        'payableAmount': float(row.payable_amount),
        'startsAt': row.starts_at.isoformat() if row.starts_at else None,
        'endsAt': row.ends_at.isoformat() if row.ends_at else None,
        'nextRenewalAt': row.next_renewal_at.isoformat() if row.next_renewal_at else None,
        'graceEndsAt': row.grace_ends_at.isoformat() if row.grace_ends_at else None,
        'accessEndsAt': access_ends.isoformat() if access_ends else None,
        'renewalFailedAttempts': row.renewal_failed_attempts,
        'warning': warning_payload(row, now, mark_warning),
    }


def question_track_for_user(user):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'acctype', '') != 'Student':
        return None
    row = current_subscription(user)
    return row.plan.track if row else None


def subsource_allowed(track, value):
    if not track or track == 'combined':
        return True
    value = (value or '').strip()
    academic = not value or value.startswith(ACADEMIC_PREFIXES)
    return academic if track == 'academic' else (bool(value) and not academic)


def entitlement_sql(track, column='subsource'):
    if not track or track == 'combined':
        return '', []
    likes = ' OR '.join([f"{column} LIKE %s" for _ in ACADEMIC_PREFIXES])
    params = [f'{prefix}%' for prefix in ACADEMIC_PREFIXES]
    if track == 'academic':
        return f"(TRIM(COALESCE({column}, '')) = '' OR {likes})", params
    return f"(TRIM(COALESCE({column}, '')) <> '' AND NOT ({likes}))", params
