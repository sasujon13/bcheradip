import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_optional_user
from app.models import Subscription, User
from app.schemas import BillingVerifyRequest, BillingVerifyResponse
from app.security import ms_in_days
from app.services import play_gateway
from app.services.promo_logic import (
    commission_for_purchase,
    compound_price,
    discount_for_code,
    price_for_product,
    slot1_active,
)
from app.services.referral_earnings import (
    USAGE_SUBSCRIPTION,
    balance_row,
    debit_available_balance,
    now_ms,
    record_pending_commission,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


def _tier_from_product(product_id: str) -> str:
    pid = product_id.lower()
    if "plus" in pid:
        return "plus"
    return "pro"


def _fallback_expiry(product_id: str) -> int:
    return ms_in_days(30 if "month" in product_id.lower() else 365)


@router.post("/verify", response_model=BillingVerifyResponse)
def verify_purchase(
    body: BillingVerifyRequest,
    db: Session = Depends(get_db),
    buyer: User | None = Depends(get_optional_user),
) -> BillingVerifyResponse:
    # Verify the purchase token with Google Play (source of truth). When Play
    # credentials are not configured we fall back to DEV mode (trust client) —
    # never leave that on in production.
    verification: play_gateway.PlayVerification | None = None
    if play_gateway.enabled():
        verification = play_gateway.verify_subscription(body.productId, body.purchaseToken)
        if verification is None:
            raise HTTPException(502, "Could not verify purchase with Google Play. Try again.")

    existing = db.scalar(
        select(Subscription).where(Subscription.purchase_token == body.purchaseToken).limit(1)
    )
    if existing:
        # Refresh entitlement from Google on repeat checks (handles renewals,
        # cancellations and expiry without waiting for an RTDN notification).
        if verification is not None:
            existing.active = verification.active
            if verification.expiry_ms:
                existing.expires_at_ms = verification.expiry_ms
            db.commit()
        return BillingVerifyResponse(
            active=existing.active,
            expiresAt=existing.expires_at_ms,
            tier=existing.tier,
        )

    if verification is not None:
        if not verification.active:
            return BillingVerifyResponse(
                active=False,
                expiresAt=verification.expiry_ms,
                tier=_tier_from_product(verification.product_id or body.productId),
            )
        product_id = verification.product_id or body.productId
        tier = _tier_from_product(product_id)
        expires = verification.expiry_ms or _fallback_expiry(product_id)
    else:
        # DEV fallback: no Play credentials configured.
        logger.warning(
            "Play verification disabled — trusting client purchase token (DEV only)."
        )
        product_id = body.productId
        tier = _tier_from_product(product_id)
        expires = _fallback_expiry(product_id)

    paid_at = now_ms()

    base = price_for_product(product_id)
    discounts: list[int] = []
    referrer_user_id: int | None = None

    if body.slot1Code and slot1_active(db, body.slot1Code):
        try:
            d1, _, _ = discount_for_code(db, body.slot1Code)
            discounts.append(d1)
        except ValueError:
            pass

    if body.slot2Code:
        try:
            d2, _, referrer = discount_for_code(
                db,
                body.slot2Code,
                slot1_code=body.slot1Code,
            )
            discounts.append(d2)
            if referrer:
                referrer_user_id = referrer.id
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    gross_amount = compound_price(base, discounts)
    requested_credit = float(body.referralBalanceUsd or 0.0)
    referral_credit = 0.0
    if buyer and requested_credit > 0:
        referral_credit = round(min(requested_credit, gross_amount), 2)
    elif requested_credit > 0:
        raise HTTPException(401, "Sign in to apply referral balance at checkout")

    if referrer_user_id and buyer and referrer_user_id == buyer.id:
        raise HTTPException(400, "You cannot use your own referral on this purchase")

    if referral_credit > 0 and buyer:
        available = balance_row(db, buyer.id).available_usd
        if referral_credit > available:
            raise HTTPException(400, "Insufficient referral balance")

    play_amount = round(max(0.0, gross_amount - referral_credit), 2)
    commission = 0.0
    if referrer_user_id and play_amount > 0:
        commission = commission_for_purchase(db, play_amount)

    subscription = Subscription(
        user_id=buyer.id if buyer else None,
        buyer_user_id=buyer.id if buyer else None,
        referrer_user_id=referrer_user_id,
        product_id=product_id,
        purchase_token=body.purchaseToken,
        tier=tier,
        active=True,
        expires_at_ms=expires,
        gross_amount_usd=gross_amount,
        net_amount_usd=play_amount,
        play_amount_usd=play_amount,
        referral_balance_used_usd=referral_credit,
        referral_commission_usd=commission,
        paid_at_ms=paid_at,
        slot1_code=body.slot1Code,
        slot2_code=body.slot2Code,
    )
    db.add(subscription)
    db.flush()

    if referral_credit > 0 and buyer:
        try:
            debit_available_balance(
                db,
                user_id=buyer.id,
                amount_usd=referral_credit,
                usage_type=USAGE_SUBSCRIPTION,
                subscription_id=subscription.id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    if referrer_user_id and commission > 0:
        record_pending_commission(
            db,
            referrer_user_id=referrer_user_id,
            subscription_id=subscription.id,
            amount_usd=commission,
            clears_at_ms=expires,
        )

    db.commit()

    # Acknowledge server-side so the purchase is never auto-refunded even if the
    # client misses its 3-day window (idempotent when already acknowledged).
    if verification is not None and not verification.acknowledged:
        play_gateway.acknowledge_subscription(body.purchaseToken)

    return BillingVerifyResponse(active=True, expiresAt=expires, tier=tier)


# Play RTDN notification types that end access (see rtdn-reference docs):
# 12 = REVOKED, 13 = EXPIRED. Used only when Google can't be re-reached.
_RTDN_EXPIRED = {12, 13}


@router.post("/rtdn")
async def play_rtdn(request: Request, db: Session = Depends(get_db)) -> dict:
    """Google Play Real-Time Developer Notifications (Cloud Pub/Sub push).

    Keeps subscription state in sync on renewal, cancellation, grace period,
    account hold, expiry and revocation. Always returns 200 so Pub/Sub does not
    retry indefinitely on messages we intentionally ignore.
    """
    if settings.google_play_rtdn_token:
        if request.query_params.get("token") != settings.google_play_rtdn_token:
            raise HTTPException(403, "Invalid RTDN token")

    payload = await request.body()
    notification = play_gateway.parse_rtdn(payload)
    if notification is None:
        return {"ok": True, "ignored": True}

    sub = db.scalar(
        select(Subscription)
        .where(Subscription.purchase_token == notification.purchase_token)
        .limit(1)
    )
    if not sub:
        # Unknown token (e.g. purchase not yet verified by the client) — re-verify
        # lazily so we still capture its current state if Play is reachable.
        return {"ok": True, "unknown": True}

    verification = play_gateway.verify_subscription(sub.product_id, notification.purchase_token)
    if verification is not None:
        sub.active = verification.active
        if verification.expiry_ms:
            sub.expires_at_ms = verification.expiry_ms
    elif notification.notification_type in _RTDN_EXPIRED:
        sub.active = False

    db.commit()
    return {"ok": True, "type": notification.notification_type, "active": sub.active}
