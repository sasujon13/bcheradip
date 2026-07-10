"""Thin Stripe wrapper. Lazy-imports so the API runs without the stripe package.

When STRIPE_SECRET_KEY is unset the gateway is "disabled": checkout falls back to
the hosted pricing page and webhooks are rejected. This keeps license-key
activation and usage tracking fully functional in dev / self-host setups.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.services.billing_types import BillingEvent
from app.services.plans import PlanDef

logger = logging.getLogger(__name__)


def stripe_enabled() -> bool:
    return bool(settings.stripe_secret_key)


def enabled() -> bool:
    """Provider-agnostic alias used by the billing facade."""
    return stripe_enabled()


def _stripe():
    import stripe  # noqa: PLC0415 — lazy so package is optional

    stripe.api_key = settings.stripe_secret_key
    return stripe


def price_id_for(plan: PlanDef) -> str | None:
    if not plan.stripe_price_env:
        return None
    return getattr(settings, plan.stripe_price_env, "") or None


def ensure_customer(email: str | None, name: str | None, existing_id: str | None) -> str | None:
    if not stripe_enabled():
        return existing_id
    if existing_id:
        return existing_id
    try:
        customer = _stripe().Customer.create(email=email or None, name=name or None)
        return customer["id"]
    except Exception as exc:  # noqa: BLE001
        logger.error("Stripe customer create failed: %s", exc)
        return existing_id


def _stringify(custom_data: dict) -> dict:
    return {k: (str(v) if v is not None else "") for k, v in custom_data.items()}


def create_subscription_checkout(
    *,
    customer_id: str | None,
    price_id: str,
    quantity: int,
    custom_data: dict,
) -> str | None:
    """Return a Stripe Checkout URL for a recurring plan, or None if disabled."""
    if not stripe_enabled():
        return None
    try:
        session = _stripe().checkout.Session.create(
            mode="subscription",
            customer=customer_id or None,
            line_items=[{"price": price_id, "quantity": max(1, quantity)}],
            success_url=settings.billing_success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=settings.billing_cancel_url,
            metadata=_stringify(custom_data),
            allow_promotion_codes=True,
        )
        return session.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.error("Stripe subscription checkout failed: %s", exc)
        return None


def create_payg_checkout(
    *,
    customer_id: str | None,
    amount_usd: float,
    team_id: int,
    charge_id: int,
) -> str | None:
    """One-off payment to settle accumulated PAYG overage immediately."""
    if not stripe_enabled():
        return None
    try:
        session = _stripe().checkout.Session.create(
            mode="payment",
            customer=customer_id or None,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": max(50, int(round(amount_usd * 100))),
                        "product_data": {"name": "Cheradip pay-as-you-go usage"},
                    },
                    "quantity": 1,
                }
            ],
            success_url=settings.billing_success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=settings.billing_cancel_url,
            metadata={"team_id": str(team_id), "charge_id": str(charge_id), "kind": "payg"},
        )
        return session.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.error("Stripe PAYG checkout failed: %s", exc)
        return None


def create_credit_checkout(
    *,
    customer_id: str | None,
    amount_usd: float,
    team_id: int,
    user_id: int,
) -> str | None:
    if not stripe_enabled():
        return None
    try:
        session = _stripe().checkout.Session.create(
            mode="payment",
            customer=customer_id or None,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": max(50, int(round(amount_usd * 100))),
                        "product_data": {"name": "Cheradip prepaid credit"},
                    },
                    "quantity": 1,
                }
            ],
            success_url=settings.billing_success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=settings.billing_cancel_url,
            metadata={
                "team_id": str(team_id),
                "user_id": str(user_id),
                "kind": "credit_topup",
            },
        )
        return session.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.error("Stripe credit checkout failed: %s", exc)
        return None


def billing_portal_url(customer_id: str | None) -> str | None:
    if not stripe_enabled() or not customer_id:
        return None
    try:
        portal = _stripe().billing_portal.Session.create(
            customer=customer_id,
            return_url=settings.billing_pricing_url,
        )
        return portal.get("url")
    except Exception as exc:  # noqa: BLE001
        logger.error("Stripe portal failed: %s", exc)
        return None


def _to_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_webhook(payload: bytes, sig_header: str | None) -> BillingEvent | None:
    """Verify + normalize a Stripe webhook into a provider-agnostic BillingEvent."""
    if not stripe_enabled() or not settings.stripe_webhook_secret:
        return None
    try:
        event = _stripe().Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Stripe webhook verify failed: %s", exc)
        return None

    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    meta = obj.get("metadata", {}) or {}

    if etype == "checkout.session.completed":
        return BillingEvent(
            type="checkout_completed",
            product=meta.get("product") or "ext",
            kind=meta.get("kind"),
            team_id=_to_int(meta.get("team_id")),
            user_id=_to_int(meta.get("user_id")),
            plan=meta.get("plan"),
            charge_id=_to_int(meta.get("charge_id")),
            amount_usd=round(float(obj.get("amount_total", 0) or 0) / 100.0, 2),
            currency=(obj.get("currency") or "usd").upper(),
            customer_id=obj.get("customer"),
            subscription_id=obj.get("subscription"),
            transaction_id=obj.get("id"),
            payment_intent=obj.get("payment_intent"),
        )
    if etype == "customer.subscription.updated":
        status = obj.get("status", "")
        norm = "active" if status in ("active", "trialing") else (
            "past_due" if status in ("past_due", "unpaid") else "canceled"
        )
        return BillingEvent(
            type="subscription_updated", subscription_id=obj.get("id"), status=norm
        )
    if etype == "customer.subscription.deleted":
        return BillingEvent(type="subscription_canceled", subscription_id=obj.get("id"))
    return BillingEvent(type="ignored")
