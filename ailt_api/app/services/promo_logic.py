"""Shared promo / referral discount rules."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import PromoCode, ReferralPolicy, User

CODES_REQUIRING_SLOT1 = frozenset({"WELCOME10"})
REFERRAL_GATE_CODE = "REFER20"

PLAY_PRICES_USD = {
    "pro_monthly": 2.0,
    "pro_yearly": 20.0,
    "plus_monthly": 5.0,
    "plus_yearly": 50.0,
}


def promo_row(db: Session, code: str) -> PromoCode | None:
    return db.scalar(select(PromoCode).where(PromoCode.code == code.upper()))


def referral_gate(db: Session) -> PromoCode | None:
    """REFER20 must exist, be active, and have discount > 0 to enable referral username discounts."""
    row = promo_row(db, REFERRAL_GATE_CODE)
    if row and row.active and row.discount_percent > 0:
        return row
    return None


def find_referrer_user(db: Session, raw: str) -> User | None:
    needle = raw.strip()
    if not needle:
        return None
    lowered = needle.lower()
    return db.scalar(
        select(User).where(
            or_(
                User.username == needle,
                User.username == lowered,
                User.email == lowered,
                User.whatsapp == needle,
            )
        )
    )


def referrer_buyer_discount(db: Session, raw: str) -> tuple[int, User] | None:
    gate = referral_gate(db)
    if not gate:
        return None
    user = find_referrer_user(db, raw)
    if not user:
        return None
    return gate.discount_percent, user


def slot1_active(db: Session, slot1_code: str | None) -> bool:
    if not slot1_code:
        return False
    row = promo_row(db, slot1_code.strip())
    return bool(row and row.active and row.discount_percent > 0 and row.auto_apply)


def discount_for_code(
    db: Session,
    raw: str,
    *,
    slot1_code: str | None = None,
) -> tuple[int, str, User | None]:
    """Returns (discount_percent, display_code, referrer_user_if_any)."""
    code = raw.strip()
    if not code:
        raise ValueError("Promo code is expired. No discount available.")

    entry = promo_row(db, code.upper())
    if entry and entry.active and entry.discount_percent > 0:
        if entry.code in CODES_REQUIRING_SLOT1 and not slot1_active(db, slot1_code):
            raise ValueError("WELCOME10 requires an active launch promo (e.g. LAUNCH50) first.")
        return entry.discount_percent, entry.code, None

    ref = referrer_buyer_discount(db, code)
    if ref:
        pct, user = ref
        return pct, code, user

    raise ValueError("Promo code is expired. No discount available.")


def compound_price(base: float, discounts: list[int]) -> float:
    price = base
    for pct in discounts:
        if pct > 0:
            price *= 1 - pct / 100
    return round(price, 2)


def price_for_product(product_id: str) -> float:
    pid = product_id.lower()
    for key, value in PLAY_PRICES_USD.items():
        if key.replace("_", "") in pid.replace(".", "").replace("-", ""):
            return value
    if "plus" in pid:
        return 50.0 if "year" in pid else 5.0
    return 20.0 if "year" in pid else 2.0


def commission_for_purchase(db: Session, amount_paid: float) -> float:
    pol = db.scalar(select(ReferralPolicy).limit(1))
    if not pol or not pol.active or pol.commission_percent <= 0:
        return 0.0
    return round(amount_paid * pol.commission_percent / 100, 2)
