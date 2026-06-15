"""Referral commission lifecycle: pending until subscription period ends, then available."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReferralBalance, ReferralBalanceUsage, ReferralEarning

USAGE_SUBSCRIPTION = "subscription"
USAGE_GIFT = "gift"
USAGE_WITHDRAW = "withdraw"


def now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


def sync_balance_usd(row: ReferralBalance) -> None:
    row.balance_usd = round(float(row.available_usd), 2)


def balance_row(db: Session, user_id: int) -> ReferralBalance:
    row = db.scalar(select(ReferralBalance).where(ReferralBalance.user_id == user_id))
    if row:
        sync_balance_usd(row)
        return row
    row = ReferralBalance(
        user_id=user_id,
        balance_usd=0.0,
        pending_usd=0.0,
        available_usd=0.0,
        lifetime_earned_usd=0.0,
    )
    db.add(row)
    db.flush()
    return row


def mature_pending_earnings(db: Session) -> None:
    """Move cleared commissions from pending to available balances."""
    cutoff = now_ms()
    rows = db.scalars(
        select(ReferralEarning).where(
            ReferralEarning.status == "pending",
            ReferralEarning.clears_at_ms <= cutoff,
        )
    ).all()
    for earning in rows:
        earning.status = "available"
        bal = balance_row(db, earning.referrer_user_id)
        bal.pending_usd = round(max(0.0, bal.pending_usd - earning.amount_usd), 2)
        bal.available_usd = round(bal.available_usd + earning.amount_usd, 2)
        sync_balance_usd(bal)


def record_pending_commission(
    db: Session,
    *,
    referrer_user_id: int,
    subscription_id: int,
    amount_usd: float,
    clears_at_ms: int,
) -> ReferralEarning | None:
    amount = round(float(amount_usd), 2)
    if amount <= 0:
        return None
    earning = ReferralEarning(
        subscription_id=subscription_id,
        referrer_user_id=referrer_user_id,
        amount_usd=amount,
        status="pending",
        clears_at_ms=clears_at_ms,
    )
    db.add(earning)
    db.flush()
    bal = balance_row(db, referrer_user_id)
    bal.pending_usd = round(bal.pending_usd + amount, 2)
    bal.lifetime_earned_usd = round(bal.lifetime_earned_usd + amount, 2)
    sync_balance_usd(bal)
    return earning


def debit_available_balance(
    db: Session,
    *,
    user_id: int,
    amount_usd: float,
    usage_type: str,
    recipient_email: str | None = None,
    subscription_id: int | None = None,
    withdrawal_id: int | None = None,
) -> float:
    amount = round(float(amount_usd), 2)
    if amount <= 0:
        return 0.0
    bal = balance_row(db, user_id)
    if amount > bal.available_usd:
        raise ValueError("Insufficient referral balance")
    bal.available_usd = round(bal.available_usd - amount, 2)
    sync_balance_usd(bal)
    db.add(
        ReferralBalanceUsage(
            user_id=user_id,
            usage_type=usage_type,
            amount_usd=amount,
            recipient_email=recipient_email,
            subscription_id=subscription_id,
            withdrawal_id=withdrawal_id,
        )
    )
    return amount


def referral_balance_snapshot(row: ReferralBalance) -> dict:
    sync_balance_usd(row)
    return {
        "balance_usd": row.balance_usd,
        "pending_usd": round(row.pending_usd, 2),
        "available_usd": round(row.available_usd, 2),
        "lifetime_earned_usd": round(row.lifetime_earned_usd, 2),
    }
