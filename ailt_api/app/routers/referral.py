from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ReferralPolicy, ReferralWithdrawal, User
from app.schemas import ReferralGiftRequest, ReferralWithdrawRequest
from app.services.referral_earnings import (
    USAGE_GIFT,
    USAGE_WITHDRAW,
    balance_row,
    debit_available_balance,
    mature_pending_earnings,
    referral_balance_snapshot,
)

router = APIRouter(prefix="/referral", tags=["referral"])

MIN_WITHDRAWAL_USD = 100.0


@router.get("/policy")
def referral_policy(db: Session = Depends(get_db)) -> dict:
    pol = db.scalar(select(ReferralPolicy).limit(1))
    if not pol:
        return {
            "commission_percent": 20,
            "notice_text": "Referral program",
            "min_withdrawal_usd": MIN_WITHDRAWAL_USD,
        }
    return {
        "commission_percent": pol.commission_percent,
        "notice_text": pol.notice_text or "Refer friends and earn rewards.",
        "min_withdrawal_usd": MIN_WITHDRAWAL_USD,
    }


@router.get("/balance")
def referral_balance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    mature_pending_earnings(db)
    row = balance_row(db, user.id)
    db.commit()
    snapshot = referral_balance_snapshot(row)
    available = snapshot["available_usd"]
    return {
        **snapshot,
        "min_withdrawal_usd": MIN_WITHDRAWAL_USD,
        "withdrawable": available >= MIN_WITHDRAWAL_USD,
    }


@router.post("/gift")
def referral_gift(
    body: ReferralGiftRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    recipient = body.recipientEmail.strip().lower()
    if "@" not in recipient:
        raise HTTPException(400, "Valid recipient email is required")
    if user.email and user.email.lower() == recipient:
        raise HTTPException(400, "Cannot gift credits to yourself")

    recipient_user = db.scalar(select(User).where(User.email == recipient))
    if not recipient_user:
        raise HTTPException(
            404,
            "Recipient must have a registered account with that email.",
        )
    if float(body.amountUsd) < 0.01:
        raise HTTPException(400, "Minimum gift amount is $0.01")

    mature_pending_earnings(db)
    try:
        amount = debit_available_balance(
            db,
            user_id=user.id,
            amount_usd=float(body.amountUsd),
            usage_type=USAGE_GIFT,
            recipient_email=recipient,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    recipient_bal = balance_row(db, recipient_user.id)
    recipient_bal.available_usd = round(recipient_bal.available_usd + amount, 2)
    from app.services.referral_earnings import sync_balance_usd

    sync_balance_usd(recipient_bal)

    db.commit()
    row = balance_row(db, user.id)
    snapshot = referral_balance_snapshot(row)
    return {
        "ok": True,
        "message": f"${amount:.2f} gifted to {recipient}.",
        **snapshot,
    }


@router.post("/withdraw")
def referral_withdraw(
    body: ReferralWithdrawRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    method = body.method.strip().lower()
    payout_details = body.payoutDetails.strip()
    if method not in {"paypal", "bank_transfer", "mobile_wallet"}:
        raise HTTPException(400, "method must be paypal, bank_transfer, or mobile_wallet")
    if len(payout_details) < 3:
        raise HTTPException(400, "payoutDetails is required")

    mature_pending_earnings(db)
    row = balance_row(db, user.id)
    amount = float(body.amountUsd if body.amountUsd is not None else row.available_usd)
    if amount < MIN_WITHDRAWAL_USD:
        raise HTTPException(400, f"Minimum withdrawal is ${MIN_WITHDRAWAL_USD:.0f}")
    if amount > row.available_usd:
        raise HTTPException(400, "Insufficient referral balance")

    withdrawal = ReferralWithdrawal(
        user_id=user.id,
        amount_usd=amount,
        method=method,
        payout_details=payout_details,
        status="pending",
    )
    db.add(withdrawal)
    db.flush()

    try:
        debit_available_balance(
            db,
            user_id=user.id,
            amount_usd=amount,
            usage_type=USAGE_WITHDRAW,
            withdrawal_id=withdrawal.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    db.commit()
    db.refresh(withdrawal)
    snapshot = referral_balance_snapshot(row)
    return {
        "ok": True,
        "message": "Withdrawal request submitted. Processing within 5–10 business days.",
        **snapshot,
        "withdrawal_id": withdrawal.id,
    }
