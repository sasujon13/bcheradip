"""Credit wallet + payment-history helpers for the Cheradip extension."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CreditBalance, CreditTransaction, ExtPayment
from app.services.plans import ms_now


def get_or_create_balance(db: Session, team_id: int) -> CreditBalance:
    row = db.scalar(select(CreditBalance).where(CreditBalance.team_id == team_id))
    if row is None:
        row = CreditBalance(team_id=team_id, updated_at_ms=ms_now())
        db.add(row)
        db.flush()
    return row


def grant_credit(
    db: Session,
    *,
    team_id: int,
    amount_usd: float,
    reason: str = "admin_grant",
    actor_user_id: int | None = None,
) -> CreditBalance:
    amount = round(float(amount_usd), 2)
    bal = get_or_create_balance(db, team_id)
    bal.balance_usd = round(bal.balance_usd + amount, 2)
    if amount >= 0:
        bal.lifetime_added_usd = round(bal.lifetime_added_usd + amount, 2)
    bal.updated_at_ms = ms_now()
    db.add(
        CreditTransaction(
            team_id=team_id,
            user_id=actor_user_id,
            delta_usd=amount,
            reason=reason,
            balance_after_usd=bal.balance_usd,
            created_at_ms=ms_now(),
        )
    )
    db.commit()
    return bal


def spend_credit(
    db: Session,
    *,
    team_id: int,
    amount_usd: float,
    reason: str = "usage",
    user_id: int | None = None,
) -> float:
    """Spend up to the available balance. Returns the amount actually spent."""
    bal = get_or_create_balance(db, team_id)
    spend = round(min(bal.balance_usd, max(0.0, amount_usd)), 2)
    if spend <= 0:
        return 0.0
    bal.balance_usd = round(bal.balance_usd - spend, 2)
    bal.lifetime_spent_usd = round(bal.lifetime_spent_usd + spend, 2)
    bal.updated_at_ms = ms_now()
    db.add(
        CreditTransaction(
            team_id=team_id,
            user_id=user_id,
            delta_usd=-spend,
            reason=reason,
            balance_after_usd=bal.balance_usd,
            created_at_ms=ms_now(),
        )
    )
    db.commit()
    return spend


def record_payment(
    db: Session,
    *,
    team_id: int,
    user_id: int | None = None,
    kind: str = "subscription",
    amount_usd: float = 0.0,
    status: str = "paid",
    plan: str | None = None,
    description: str | None = None,
    stripe_payment_intent: str | None = None,
    stripe_invoice_id: str | None = None,
    stripe_session_id: str | None = None,
) -> ExtPayment:
    payment = ExtPayment(
        team_id=team_id,
        user_id=user_id,
        kind=kind,
        plan=plan,
        amount_usd=round(float(amount_usd), 2),
        status=status,
        description=description,
        stripe_payment_intent=stripe_payment_intent,
        stripe_invoice_id=stripe_invoice_id,
        stripe_session_id=stripe_session_id,
        created_at_ms=ms_now(),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment
