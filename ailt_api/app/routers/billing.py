from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_optional_user
from app.models import Subscription, User
from app.schemas import BillingVerifyRequest, BillingVerifyResponse
from app.security import ms_in_days
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

router = APIRouter(prefix="/billing", tags=["billing"])


def _tier_from_product(product_id: str) -> str:
    pid = product_id.lower()
    if "plus" in pid:
        return "plus"
    return "pro"


@router.post("/verify", response_model=BillingVerifyResponse)
def verify_purchase(
    body: BillingVerifyRequest,
    db: Session = Depends(get_db),
    buyer: User | None = Depends(get_optional_user),
) -> BillingVerifyResponse:
    existing = db.scalar(
        select(Subscription).where(Subscription.purchase_token == body.purchaseToken).limit(1)
    )
    if existing:
        return BillingVerifyResponse(
            active=existing.active,
            expiresAt=existing.expires_at_ms,
            tier=existing.tier,
        )

    # Play Billing verification stub — store entitlement locally until Play API wired
    tier = _tier_from_product(body.productId)
    expires = ms_in_days(30 if "month" in body.productId.lower() else 365)
    paid_at = now_ms()

    base = price_for_product(body.productId)
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
        product_id=body.productId,
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
    return BillingVerifyResponse(active=True, expiresAt=expires, tier=tier)
