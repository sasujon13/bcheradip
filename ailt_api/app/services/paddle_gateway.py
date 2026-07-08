"""Paddle Billing gateway (Merchant of Record).

Paddle is the seller of record: it charges customers' cards worldwide, handles
sales tax/VAT, and pays the balance out to the seller (wire / Payoneer). This is
the default because Stripe/PayPal do not onboard sellers in Bangladesh.

When ``paddle_api_key`` is unset the gateway is "disabled": checkout falls back
to the hosted pricing page and webhooks are rejected — so license-key activation
and usage tracking still work in dev.

Docs: https://developer.paddle.com/  (Paddle Billing, not Paddle Classic)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx

from app.services import runtime_config
from app.services.billing_types import BillingEvent
from app.services.plans import PlanDef

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0


def _api_key() -> str:
    return runtime_config.get("paddle_api_key")


def _environment() -> str:
    return runtime_config.get("paddle_environment", "sandbox")


def _webhook_secret() -> str:
    return runtime_config.get("paddle_webhook_secret")


def client_token() -> str:
    """Publishable client-side token (safe for the pricing page)."""
    return runtime_config.get("paddle_client_token")


def enabled() -> bool:
    return bool(_api_key())


def _base_url() -> str:
    if (_environment() or "sandbox").lower().startswith("prod"):
        return "https://api.paddle.com"
    return "https://sandbox-api.paddle.com"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, payload: dict | None = None) -> dict | None:
    if not enabled():
        return None
    url = _base_url() + path
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.request(method, url, headers=_headers(), json=payload)
        if resp.status_code >= 400:
            logger.error("Paddle %s %s -> %s: %s", method, path, resp.status_code, resp.text[:500])
            return None
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.error("Paddle request %s %s failed: %s", method, path, exc)
        return None


def price_id_for(plan: PlanDef) -> str | None:
    if plan.id in ("pro", "plus", "business"):
        return runtime_config.get(f"paddle_price_{plan.id}") or None
    return None


def verify_credentials(api_key: str, environment: str) -> tuple[bool, str]:
    """Live-test a Paddle API key against Paddle before saving it.

    Returns (ok, message). Used by the admin config page so the operator gets a
    clear success/error result instead of silently storing a bad key.
    """
    if not api_key:
        return False, "API key is required"
    base = (
        "https://api.paddle.com"
        if (environment or "sandbox").lower().startswith("prod")
        else "https://sandbox-api.paddle.com"
    )
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(
                base + "/event-types",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not reach Paddle: {exc}"
    if resp.status_code == 200:
        return True, "Paddle credentials verified"
    if resp.status_code in (401, 403):
        return False, "Paddle rejected the API key (check key and environment)"
    return False, f"Paddle returned HTTP {resp.status_code}"


def get_customer_email(customer_id: str | None) -> str | None:
    """Look up a Paddle customer's email (used to link anonymous web checkouts)."""
    if not customer_id or not enabled():
        return None
    res = _request("GET", f"/customers/{customer_id}")
    if res and res.get("data"):
        return res["data"].get("email")
    return None


def ensure_customer(email: str | None, name: str | None, existing_id: str | None) -> str | None:
    if not enabled() or existing_id:
        return existing_id
    if not email:
        return existing_id
    # Reuse an existing Paddle customer with this email if there is one.
    found = _request("GET", f"/customers?email={email}")
    if found and found.get("data"):
        return found["data"][0].get("id") or existing_id
    created = _request("POST", "/customers", {"email": email, "name": name or None})
    if created and created.get("data"):
        return created["data"].get("id")
    return existing_id


def _checkout_url(txn: dict | None) -> str | None:
    if not txn:
        return None
    data = txn.get("data", {})
    checkout = data.get("checkout") or {}
    return checkout.get("url")


def _stringify(custom_data: dict) -> dict:
    return {k: (str(v) if v is not None else "") for k, v in custom_data.items()}


def create_subscription_checkout(
    *,
    customer_id: str | None,
    price_id: str,
    quantity: int,
    custom_data: dict,
) -> str | None:
    """Create a Paddle transaction for a recurring plan; return its checkout URL."""
    payload: dict = {
        "items": [{"price_id": price_id, "quantity": max(1, quantity)}],
        "custom_data": _stringify(custom_data),
    }
    if customer_id:
        payload["customer_id"] = customer_id
    return _checkout_url(_request("POST", "/transactions", payload))


def create_payg_checkout(
    *,
    customer_id: str | None,
    amount_usd: float,
    team_id: int,
    charge_id: int,
) -> str | None:
    """One-off, non-catalog charge to settle accumulated PAYG overage now."""
    minor = max(50, int(round(amount_usd * 100)))
    payload: dict = {
        "items": [
            {
                "quantity": 1,
                "price": {
                    "description": "Cheradip pay-as-you-go usage",
                    "unit_price": {"amount": str(minor), "currency_code": "USD"},
                    "product": {"name": "Cheradip pay-as-you-go", "tax_category": "standard"},
                },
            }
        ],
        "custom_data": {"team_id": str(team_id), "charge_id": str(charge_id), "kind": "payg"},
    }
    if customer_id:
        payload["customer_id"] = customer_id
    return _checkout_url(_request("POST", "/transactions", payload))


def billing_portal_url(customer_id: str | None) -> str | None:
    if not enabled() or not customer_id:
        return None
    res = _request("POST", f"/customers/{customer_id}/portal-sessions", {})
    if not res:
        return None
    urls = res.get("data", {}).get("urls", {}) or {}
    general = urls.get("general", {}) or {}
    return general.get("overview")


def _verify_signature(payload: bytes, sig_header: str | None) -> bool:
    secret = _webhook_secret()
    if not secret or not sig_header:
        return False
    ts = None
    h1 = None
    for part in sig_header.split(";"):
        key, _, val = part.partition("=")
        if key.strip() == "ts":
            ts = val.strip()
        elif key.strip() == "h1":
            h1 = val.strip()
    if not ts or not h1:
        return False
    signed = f"{ts}:".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, h1)


def _norm_sub_status(status: str) -> str:
    s = (status or "").lower()
    if s in ("active", "trialing"):
        return "active"
    if s in ("past_due", "paused"):
        return "past_due"
    if s in ("canceled", "cancelled"):
        return "canceled"
    return s


def _to_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_webhook(payload: bytes, sig_header: str | None) -> BillingEvent | None:
    """Verify + normalize a Paddle webhook into a provider-agnostic BillingEvent."""
    if not enabled() or not _verify_signature(payload, sig_header):
        return None
    try:
        event = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("Paddle webhook JSON parse failed: %s", exc)
        return None

    etype = event.get("event_type", "")
    data = event.get("data", {}) or {}
    custom = data.get("custom_data") or {}

    if etype in ("transaction.completed", "transaction.paid"):
        totals = (data.get("details", {}) or {}).get("totals", {}) or {}
        grand = totals.get("grand_total") or "0"
        try:
            amount = round(int(grand) / 100.0, 2)
        except (TypeError, ValueError):
            amount = 0.0
        return BillingEvent(
            type="checkout_completed",
            product=custom.get("product") or "ext",
            kind=custom.get("kind"),
            team_id=_to_int(custom.get("team_id")),
            user_id=_to_int(custom.get("user_id")),
            plan=custom.get("plan"),
            charge_id=_to_int(custom.get("charge_id")),
            amount_usd=amount,
            currency=data.get("currency_code", "USD"),
            customer_id=data.get("customer_id"),
            subscription_id=data.get("subscription_id"),
            transaction_id=data.get("id"),
            payment_intent=data.get("id"),
        )

    if etype in ("subscription.updated", "subscription.activated", "subscription.resumed"):
        return BillingEvent(
            type="subscription_updated",
            product=custom.get("product") or "ext",
            subscription_id=data.get("id"),
            status=_norm_sub_status(data.get("status", "")),
        )

    if etype in ("subscription.canceled", "subscription.cancelled"):
        return BillingEvent(
            type="subscription_canceled",
            product=custom.get("product") or "ext",
            subscription_id=data.get("id"),
        )

    return BillingEvent(type="ignored")
