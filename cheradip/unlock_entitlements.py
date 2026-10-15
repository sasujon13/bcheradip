"""Time-limited coin unlocks and subscription-backed institute access."""

import json

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .membership import add_months
from .models import Customer
from .package_service import active_subscriptions


QUESTION_KEYS = 'unlocked_question_keys'
QUESTION_EXPIRIES = 'unlocked_question_expires_at_v1'
INSTITUTE_KEYS = 'unlocked_ntrca_eiins_v2'
INSTITUTE_EXPIRIES = 'unlocked_ntrca_eiin_expires_at_v1'
PACKAGE_INSTITUTES = 'package_unlocked_ntrca_eiins_v1'
COIN_UNLOCK_MONTHS = 24


def active_coin_unlocks(settings, key_name, expiry_name, now=None):
    """Prune expired grants; give undated legacy purchases one final 24-month term."""
    now = now or timezone.now()
    raw_keys = settings.get(key_name)
    raw_expiries = settings.get(expiry_name)
    if raw_keys is None and raw_expiries is None:
        return set()
    keys = {str(key).strip() for key in raw_keys} if isinstance(raw_keys, list) else set()
    keys.discard('')
    expiries = raw_expiries if isinstance(raw_expiries, dict) else {}
    active = {}
    for key in keys:
        raw_deadline = expiries.get(key)
        if raw_deadline is None:
            # Older purchases have no recorded date. Do not silently revoke them.
            deadline = add_months(now, COIN_UNLOCK_MONTHS)
        else:
            deadline = parse_datetime(raw_deadline) if isinstance(raw_deadline, str) else None
            if deadline is None or timezone.is_naive(deadline):
                continue
        if deadline > now:
            active[key] = deadline.isoformat()
    settings[key_name] = sorted(active)
    settings[expiry_name] = active
    return set(active)


def grant_coin_unlock(settings, key_name, expiry_name, key, now=None):
    now = now or timezone.now()
    keys = active_coin_unlocks(settings, key_name, expiry_name, now)
    key = str(key).strip()
    if key:
        keys.add(key)
        settings.setdefault(expiry_name, {})
        settings[expiry_name][key] = add_months(now, COIN_UNLOCK_MONTHS).isoformat()
        settings[key_name] = sorted(keys)
    return keys


def migrate_unlock_settings(customer, now=None):
    """Persist lazy migration without overwriting a concurrent wallet change."""
    now = now or timezone.now()
    with transaction.atomic():
        locked = Customer.objects.select_for_update().get(pk=customer.pk)
        raw = locked.settings
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                raw = {}
        data = dict(raw) if isinstance(raw, dict) else {}
        before = dict(data)
        active_coin_unlocks(data, QUESTION_KEYS, QUESTION_EXPIRIES, now)
        active_coin_unlocks(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES, now)
        if data != before:
            locked.settings = data
            locked.save(update_fields=['settings'])
        customer.settings = data
    return data


def has_active_paid_package(customer, now=None):
    if not getattr(customer, 'is_authenticated', False) or not getattr(customer, 'pk', None):
        return False
    return any(row.plan.price > 0 for row in active_subscriptions(customer, now=now))


def effective_institute_eiins(customer, request=None):
    """Only clicked institutes: active coin grants plus active-plan grants."""
    if not getattr(customer, 'is_authenticated', False):
        return set()
    cache_name = '_cheradip_effective_institute_eiins'
    if request is not None and hasattr(request, cache_name):
        return getattr(request, cache_name)
    paid_plan = has_active_paid_package(customer)
    if getattr(customer, 'pk', None):
        data = migrate_unlock_settings(customer)
    else:
        data = dict(getattr(customer, 'settings', None) or {})
        active_coin_unlocks(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES)
    effective = set(data.get(INSTITUTE_KEYS) or [])
    package_eiins = data.get(PACKAGE_INSTITUTES)
    if paid_plan and isinstance(package_eiins, list):
        effective.update(str(eiin) for eiin in package_eiins)
    if request is not None:
        setattr(request, cache_name, effective)
    return effective
