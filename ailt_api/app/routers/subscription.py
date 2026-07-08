"""Cursor-style subscription + billing API for the Cheradip VS Code extension.

Separate from the Android Play-Billing routes in ``billing.py``. Endpoints:

  GET  /subscription/plans           public plan catalog (pricing UI)
  POST /subscription/license/verify  validate a license key (extension client)
  GET  /subscription/me              authed: my team plan + usage
  POST /subscription/checkout        authed: start checkout for a plan (Paddle/Stripe)
  POST /subscription/payg/enable     authed: toggle pay-as-you-go add-on
  POST /subscription/payg/checkout   authed: pay accumulated PAYG overage now
  POST /subscription/usage           authed: record usage + quota/PAYG gating
  GET  /subscription/portal          authed: billing/customer portal URL
  POST /subscription/webhook         processor webhook (subscription/payment events)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_ext_user
from app.ext_database import get_ext_db
from app.models import BillingTeam, ExtPayment, ExtUser, PaygCharge
from app.schemas import (
    LicenseVerifyRequest,
    PaygEnableRequest,
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
    UsageRecordRequest,
)
from app.services import billing_gateway, paddle_gateway, runtime_config
from app.services.billing_types import BillingEvent
from app.services.credits import record_payment
from app.services.plans import current_period_bounds, get_plan, public_catalog
from app.services.team_billing import (
    get_or_create_team,
    open_payg_charge,
    record_usage,
    usage_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscription", tags=["subscription"])


@router.get("/plans")
def plans() -> dict:
    """Public plan catalog + publishable checkout config (no secrets).

    The pricing page and the extension use ``checkout`` to init Paddle.js in the
    browser (overlay checkout). Only the publishable client token + price ids are
    exposed here — the API key / webhook secret never leave the server.
    """
    prov = billing_gateway.provider()
    checkout = {
        "provider": prov,
        "enabled": billing_gateway.enabled(),
        "environment": runtime_config.get("paddle_environment", "sandbox"),
        "clientToken": paddle_gateway.client_token() if prov == "paddle" else "",
        "prices": {
            "pro": runtime_config.get("paddle_price_pro"),
            "plus": runtime_config.get("paddle_price_plus"),
            "business": runtime_config.get("paddle_price_business"),
        },
    }
    return {
        "plans": public_catalog(),
        "provider": prov,
        "billingEnabled": billing_gateway.enabled(),
        "stripeEnabled": billing_gateway.enabled(),  # back-compat
        "pricingUrl": billing_gateway.pricing_url(),
        "checkout": checkout,
    }


@router.post("/license/verify")
def verify_license(body: LicenseVerifyRequest, db: Session = Depends(get_ext_db)) -> dict:
    key = body.licenseKey.strip()
    team = db.scalar(select(BillingTeam).where(BillingTeam.license_key == key).limit(1))
    if not team:
        return {"valid": False, "plan": "free", "status": "invalid"}
    owner = db.get(ExtUser, team.owner_user_id)
    summary = usage_summary(db, team, None)
    summary.update(
        {
            "valid": True,
            "ownerEmail": owner.email if owner else None,
        }
    )
    return summary


@router.get("/me")
def me(user: ExtUser = Depends(get_current_ext_user), db: Session = Depends(get_ext_db)) -> dict:
    team = get_or_create_team(db, user)
    return usage_summary(db, team, user)


@router.post("/checkout", response_model=SubscriptionCheckoutResponse)
def checkout(
    body: SubscriptionCheckoutRequest,
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> SubscriptionCheckoutResponse:
    plan = get_plan(body.plan)
    if plan.id == "free":
        raise HTTPException(400, "Free plan does not require checkout")

    team = get_or_create_team(db, user)
    if team.owner_user_id != user.id:
        raise HTTPException(403, "Only the team owner can change the plan")

    team.payg_enabled = body.enablePayg
    team.seats = max(body.seats, 1)
    prov = billing_gateway.provider()

    if not billing_gateway.enabled():
        db.commit()
        return SubscriptionCheckoutResponse(
            ok=True,
            checkoutUrl=None,
            pricingUrl=billing_gateway.pricing_url(),
            billingEnabled=False,
            stripeEnabled=False,
            provider=prov,
            message="Billing not configured — complete purchase on the pricing page.",
        )

    price_id = billing_gateway.price_id_for(plan)
    if not price_id:
        raise HTTPException(500, f"{prov} price id not configured for plan '{plan.id}'")

    team.stripe_customer_id = billing_gateway.ensure_customer(
        user.email, user.full_name, team.stripe_customer_id
    )
    db.commit()

    url = billing_gateway.create_subscription_checkout(
        customer_id=team.stripe_customer_id,
        price_id=price_id,
        quantity=team.seats,
        custom_data={
            "product": "ext",
            "team_id": team.id,
            "plan": plan.id,
            "kind": "subscription",
        },
    )
    if not url:
        raise HTTPException(502, f"Failed to create {prov} checkout")
    return SubscriptionCheckoutResponse(
        ok=True, checkoutUrl=url, billingEnabled=True, stripeEnabled=True, provider=prov
    )


@router.post("/payg/enable")
def payg_enable(
    body: PaygEnableRequest,
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> dict:
    team = get_or_create_team(db, user)
    if team.owner_user_id != user.id:
        raise HTTPException(403, "Only the team owner can change PAYG")
    if body.enabled and get_plan(team.plan).id == "free":
        raise HTTPException(400, "Pay-as-you-go requires a Pro, Plus, or Business plan")
    team.payg_enabled = body.enabled
    db.commit()
    return {"ok": True, "paygEnabled": team.payg_enabled}


@router.post("/payg/checkout", response_model=SubscriptionCheckoutResponse)
def payg_checkout(
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> SubscriptionCheckoutResponse:
    team = get_or_create_team(db, user)
    if team.owner_user_id != user.id:
        raise HTTPException(403, "Only the team owner can settle PAYG")
    charge = open_payg_charge(db, team)
    if charge.amount_usd <= 0:
        return SubscriptionCheckoutResponse(ok=True, message="No outstanding usage to pay")

    prov = billing_gateway.provider()
    if not billing_gateway.enabled():
        return SubscriptionCheckoutResponse(
            ok=True,
            pricingUrl=billing_gateway.pricing_url(),
            billingEnabled=False,
            stripeEnabled=False,
            provider=prov,
            message="Billing not configured — settle PAYG on the pricing page.",
        )

    url = billing_gateway.create_payg_checkout(
        customer_id=team.stripe_customer_id,
        amount_usd=charge.amount_usd,
        team_id=team.id,
        charge_id=charge.id,
    )
    if not url:
        raise HTTPException(502, f"Failed to create {prov} PAYG checkout")
    return SubscriptionCheckoutResponse(
        ok=True, checkoutUrl=url, billingEnabled=True, stripeEnabled=True, provider=prov
    )


@router.post("/usage")
def usage(
    body: UsageRecordRequest,
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> dict:
    team = get_or_create_team(db, user)
    return record_usage(db, team, user, body.requests, body.tokens, body.total_lines)


@router.get("/payments")
def my_payments(
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> dict:
    """Payment history for the signed-in user's team (customer view)."""
    team = get_or_create_team(db, user)
    rows = db.scalars(
        select(ExtPayment)
        .where(ExtPayment.team_id == team.id)
        .order_by(ExtPayment.id.desc())
        .limit(100)
    ).all()
    return {
        "payments": [
            {
                "id": p.id,
                "kind": p.kind,
                "plan": p.plan,
                "amountUsd": p.amount_usd,
                "currency": p.currency,
                "status": p.status,
                "description": p.description,
                "createdAtMs": p.created_at_ms,
            }
            for p in rows
        ]
    }


@router.get("/portal")
def portal(user: ExtUser = Depends(get_current_ext_user), db: Session = Depends(get_ext_db)) -> dict:
    team = get_or_create_team(db, user)
    url = billing_gateway.billing_portal_url(team.stripe_customer_id)
    return {"url": url or billing_gateway.pricing_url()}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_ext_db)) -> dict:
    """Paddle/Stripe webhook for the Cheradip coding extension (subscription events)."""
    payload = await request.body()
    # Paddle sends "Paddle-Signature"; Stripe sends "Stripe-Signature".
    sig = request.headers.get("paddle-signature") or request.headers.get("stripe-signature")
    event = billing_gateway.parse_webhook(payload, sig)
    if event is None:
        raise HTTPException(400, "Invalid or unverifiable webhook")

    if event.type == "checkout_completed":
        _apply_checkout_completed(db, event)
    elif event.type in ("subscription_updated", "subscription_canceled"):
        _apply_subscription_change(db, event)
    return {"received": True}


def _resolve_team_by_email(db: Session, ev: BillingEvent) -> BillingTeam | None:
    """Web (pricing-page) checkouts have no team_id — link by Paddle customer email.

    Find or create an ext_user for the buyer's email, then return their team. New
    web accounts have no password; the buyer sets one via "forgot password" (and
    their license key is shown after sign-in / on the account page).
    """
    email = paddle_gateway.get_customer_email(ev.customer_id)
    if not email:
        return None
    email = email.strip().lower()
    user = db.scalar(select(ExtUser).where(ExtUser.email == email))
    if not user:
        base = email.split("@")[0]
        username = base
        suffix = 1
        while db.scalar(select(ExtUser).where(ExtUser.username == username)):
            suffix += 1
            username = f"{base}{suffix}"
        user = ExtUser(
            email=email,
            username=username,
            role="user",
            email_verified=True,
            active=True,
        )
        db.add(user)
        db.flush()
    return get_or_create_team(db, user)


def _apply_checkout_completed(db: Session, ev: BillingEvent) -> None:
    team = db.get(BillingTeam, ev.team_id) if ev.team_id is not None else None
    if team is None:
        # Anonymous web checkout from the pricing page — link the buyer by email.
        team = _resolve_team_by_email(db, ev)
    if not team:
        logger.warning("Checkout completed but no team resolved (txn=%s)", ev.transaction_id)
        return
    start_ms, end_ms = current_period_bounds()

    if ev.kind == "subscription":
        plan = get_plan(ev.plan or "pro")
        team.plan = plan.id
        team.status = "active"
        team.stripe_subscription_id = ev.subscription_id or team.stripe_subscription_id
        team.stripe_customer_id = ev.customer_id or team.stripe_customer_id
        team.current_period_start_ms = start_ms
        team.current_period_end_ms = end_ms
        team.payg_due_usd = 0.0
        record_payment(
            db,
            team_id=team.id,
            user_id=team.owner_user_id,
            kind="subscription",
            plan=plan.id,
            amount_usd=ev.amount_usd or plan.price_usd,
            status="paid",
            description=f"{plan.name} plan subscription",
            stripe_session_id=ev.transaction_id,
            stripe_payment_intent=ev.payment_intent,
        )
    elif ev.kind == "payg":
        charge_amount = ev.amount_usd
        if ev.charge_id is not None:
            charge = db.get(PaygCharge, ev.charge_id)
            if charge:
                charge.status = "paid"
                charge.stripe_payment_intent = ev.payment_intent
                charge_amount = ev.amount_usd or charge.amount_usd
        team.payg_due_usd = 0.0
        record_payment(
            db,
            team_id=team.id,
            user_id=team.owner_user_id,
            kind="payg",
            amount_usd=charge_amount,
            status="paid",
            description="Pay-as-you-go usage settlement",
            stripe_session_id=ev.transaction_id,
            stripe_payment_intent=ev.payment_intent,
        )
    db.commit()


def _apply_subscription_change(db: Session, ev: BillingEvent) -> None:
    if not ev.subscription_id:
        return
    team = db.scalar(
        select(BillingTeam).where(BillingTeam.stripe_subscription_id == ev.subscription_id).limit(1)
    )
    if not team:
        return
    if ev.type == "subscription_canceled" or ev.status == "canceled":
        team.status = "canceled"
        team.plan = "free"
    elif ev.status == "active":
        team.status = "active"
    elif ev.status == "past_due":
        team.status = "past_due"
    db.commit()
