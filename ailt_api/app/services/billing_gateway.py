"""Provider-agnostic billing facade.

Dispatches to the configured processor (``settings.billing_provider``):
  - "paddle" (default) — Merchant of Record, works from Bangladesh, wire/Payoneer payout
  - "stripe" — optional fallback (not usable from Bangladesh)

The subscription router imports only this module, so switching processors is a
config change, not a code change.
"""

from __future__ import annotations

from app.config import settings
from app.services import paddle_gateway, stripe_gateway
from app.services.billing_types import BillingEvent
from app.services.plans import PlanDef


def provider() -> str:
    return (settings.billing_provider or "paddle").lower()


def _mod():
    return stripe_gateway if provider() == "stripe" else paddle_gateway


def enabled() -> bool:
    return _mod().enabled()


def price_id_for(plan: PlanDef) -> str | None:
    return _mod().price_id_for(plan)


def ensure_customer(email: str | None, name: str | None, existing_id: str | None) -> str | None:
    return _mod().ensure_customer(email, name, existing_id)


def create_subscription_checkout(
    *, customer_id: str | None, price_id: str, quantity: int, custom_data: dict
) -> str | None:
    return _mod().create_subscription_checkout(
        customer_id=customer_id,
        price_id=price_id,
        quantity=quantity,
        custom_data=custom_data,
    )


def create_payg_checkout(
    *, customer_id: str | None, amount_usd: float, team_id: int, charge_id: int
) -> str | None:
    return _mod().create_payg_checkout(
        customer_id=customer_id, amount_usd=amount_usd, team_id=team_id, charge_id=charge_id
    )


def create_credit_checkout(
    *, customer_id: str | None, amount_usd: float, team_id: int, user_id: int
) -> str | None:
    fn = getattr(_mod(), "create_credit_checkout", None)
    if fn is None:
        return None
    return fn(customer_id=customer_id, amount_usd=amount_usd, team_id=team_id, user_id=user_id)


def billing_portal_url(customer_id: str | None) -> str | None:
    return _mod().billing_portal_url(customer_id)


def parse_webhook(payload: bytes, sig_header: str | None) -> BillingEvent | None:
    return _mod().parse_webhook(payload, sig_header)


def pricing_url() -> str:
    return settings.billing_pricing_url
