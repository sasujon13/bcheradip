from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PromoCode, ReferralPolicy
from app.schemas import PromoValidateRequest
from app.services.promo_logic import (
    compound_price,
    discount_for_code,
    referral_gate,
    slot1_active,
)

router = APIRouter(prefix="/promo", tags=["promo"])


@router.get("/paywall-config")
def paywall_config(db: Session = Depends(get_db)) -> dict:
    promos = db.scalars(select(PromoCode).where(PromoCode.active.is_(True))).all()
    launch = next((p for p in promos if p.auto_apply and p.paywall_slot == 1), None)
    manual_active = any(p.paywall_slot == 2 and p.discount_percent > 0 for p in promos)
    gate = referral_gate(db)
    referral_active = gate is not None
    launch_active = bool(launch and launch.discount_percent > 0)
    show = launch_active or manual_active or referral_active
    return {
        "showPromoSection": show,
        "slot1": {
            "code": launch.code if launch else "",
            "visible": launch_active,
            "discountPercent": launch.discount_percent if launch else 0,
            "readOnly": True,
            "label": "Launch promo (applied automatically)",
        },
        "slot2": {
            "visible": show and (manual_active or referral_active),
            "manualEntry": True,
            "label": "Additional promo or referrer",
            "placeholder": "Referrer username, WELCOME10…",
        },
        "maxPromoCodesAtCheckout": 2,
        "referralActive": referral_active,
        "referrerBuyerDiscountPercent": gate.discount_percent if gate else 0,
    }


@router.post("/validate")
def validate_promo(body: PromoValidateRequest, db: Session = Depends(get_db)) -> dict:
    try:
        discount, out_code, referrer = discount_for_code(
            db,
            body.code,
            slot1_code=body.slot1_code,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    slot1_pct = 0
    if body.slot1_code and slot1_active(db, body.slot1_code):
        row = db.scalar(select(PromoCode).where(PromoCode.code == body.slot1_code.upper()))
        slot1_pct = row.discount_percent if row else 0

    # Slot-2 validation only — client applies compound pricing with slot1 separately.
    price = compound_price(body.base_price, [slot1_pct, discount]) if slot1_pct else compound_price(
        body.base_price,
        [discount],
    )
    return {
        "code": out_code,
        "discount_percent": discount,
        "discounted_price": f"{price:.2f}",
        "is_referrer": referrer is not None,
    }
