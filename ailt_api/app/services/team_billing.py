"""Team resolution, usage aggregation, and PAYG evaluation for the extension."""

from __future__ import annotations

import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillingTeam, CreditBalance, ExtUser, PaygCharge, TeamMember, UsageRecord
from app.services.credits import spend_credit
from app.services.free_extension import free_extension_summary
from app.services.plans import (
    PAYG_LINE_UNIT_USD,
    PAYG_UNIT_USD,
    current_period_bounds,
    get_plan,
    ms_now,
    next_plan,
    payg_gap_usd,
)
from app.services.quota_engine import can_start_new_request, evaluate_after_usage, payg_payment_threshold_usd


def new_license_key() -> str:
    raw = secrets.token_hex(9).upper()  # 18 hex chars
    return f"CHERADIP-{raw[0:6]}-{raw[6:12]}-{raw[12:18]}"


def get_or_create_team(db: Session, user: ExtUser) -> BillingTeam:
    """Return the team the user belongs to, creating a solo free team if none."""
    member = db.scalar(select(TeamMember).where(TeamMember.user_id == user.id).limit(1))
    if member:
        team = db.get(BillingTeam, member.team_id)
        if team:
            return team

    team = BillingTeam(
        name=(user.full_name or user.username or "My Team"),
        owner_user_id=user.id,
        plan="free",
        payg_enabled=False,
        status="active",
        seats=1,
        license_key=new_license_key(),
    )
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(team)
    return team


def _period_record(db: Session, team_id: int, user_id: int | None, start_ms: int) -> UsageRecord:
    rec = db.scalar(
        select(UsageRecord)
        .where(
            UsageRecord.team_id == team_id,
            UsageRecord.period_start_ms == start_ms,
            (UsageRecord.user_id == user_id)
            if user_id is not None
            else UsageRecord.user_id.is_(None),
        )
        .limit(1)
    )
    if rec is None:
        rec = UsageRecord(
            team_id=team_id,
            user_id=user_id,
            period_start_ms=start_ms,
            requests=0,
            tokens=0,
            overage_units=0,
            overage_usd=0.0,
            updated_at_ms=ms_now(),
        )
        db.add(rec)
        db.flush()
    return rec


def team_period_requests(db: Session, team_id: int, start_ms: int) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(UsageRecord.requests), 0)).where(
            UsageRecord.team_id == team_id,
            UsageRecord.period_start_ms == start_ms,
            UsageRecord.user_id.isnot(None),
        )
    )
    return int(total or 0)


def team_period_lines(db: Session, team_id: int, start_ms: int) -> int:
    """Team-wide line edits (replacements + insertions) this period."""
    total = db.scalar(
        select(func.coalesce(func.sum(UsageRecord.line_edits), 0)).where(
            UsageRecord.team_id == team_id,
            UsageRecord.period_start_ms == start_ms,
            UsageRecord.user_id.isnot(None),
        )
    )
    return int(total or 0)


def _overage_billing(plan_id: str, team_requests: int, team_lines: int) -> dict:
    """Compute request/line overage and the PAYG bill (max of the two dimensions)."""
    plan = get_plan(plan_id)
    req_over = max(0, team_requests - plan.request_quota)
    line_over = max(0, team_lines - plan.line_quota)
    req_bill = round(req_over * PAYG_UNIT_USD, 2)
    line_bill = round(line_over * PAYG_LINE_UNIT_USD, 2)
    return {
        "reqOver": req_over,
        "lineOver": line_over,
        "reqBillUsd": req_bill,
        "lineBillUsd": line_bill,
        "billUsd": round(max(req_bill, line_bill), 2),
        # Line edits are the first-priority limit; requests are the fallback.
        "lineExhausted": team_lines >= plan.line_quota,
        "reqExhausted": team_requests >= plan.request_quota,
    }


def usage_summary(db: Session, team: BillingTeam, user: ExtUser | None) -> dict:
    start_ms, end_ms = current_period_bounds()
    plan = get_plan(team.plan)
    team_used = team_period_requests(db, team.id, start_ms)
    team_lines = team_period_lines(db, team.id, start_ms)

    per_user = []
    rows = db.scalars(
        select(UsageRecord).where(
            UsageRecord.team_id == team.id,
            UsageRecord.period_start_ms == start_ms,
            UsageRecord.user_id.isnot(None),
        )
    ).all()
    for r in rows:
        member = db.get(ExtUser, r.user_id) if r.user_id else None
        per_user.append(
            {
                "userId": r.user_id,
                "email": member.email if member else None,
                "requests": r.requests,
                "lineEdits": r.line_edits,
                "tokens": r.tokens,
            }
        )

    bill = _overage_billing(team.plan, team_used, team_lines)
    gap = payg_gap_usd(team.plan)
    nxt = next_plan(team.plan)
    credit = db.scalar(select(CreditBalance.balance_usd).where(CreditBalance.team_id == team.id))
    credit_usd = round(float(credit or 0.0), 2)

    my_requests = 0
    my_lines = 0
    if user is not None:
        mine = db.scalar(
            select(UsageRecord).where(
                UsageRecord.team_id == team.id,
                UsageRecord.period_start_ms == start_ms,
                UsageRecord.user_id == user.id,
            )
        )
        if mine:
            my_requests = int(mine.requests or 0)
            my_lines = int(mine.line_edits or 0)

    return {
        "plan": team.plan,
        "planName": plan.name,
        "status": team.status,
        "paygEnabled": team.payg_enabled,
        "seats": team.seats,
        "licenseKey": team.license_key,
        "periodStartMs": start_ms,
        "periodEndMs": team.current_period_end_ms or end_ms,
        "quota": plan.request_quota,
        "lineQuota": plan.line_quota,
        "teamRequests": team_used,
        "teamLines": team_lines,
        "myRequests": my_requests,
        "myLines": my_lines,
        "overageUnits": bill["reqOver"],
        "lineOverageUnits": bill["lineOver"],
        "requestBillUsd": bill["reqBillUsd"],
        "lineBillUsd": bill["lineBillUsd"],
        "overageUsd": bill["billUsd"],
        "paygDueUsd": round(team.payg_due_usd, 2),
        "paygUnitUsd": PAYG_UNIT_USD,
        "paygLineUnitUsd": PAYG_LINE_UNIT_USD,
        "creditBalanceUsd": credit_usd,
        "nextPlan": nxt.id if nxt else None,
        "nextPlanPriceUsd": nxt.price_usd if nxt else None,
        "upgradeGapUsd": gap,
        "paygThresholdUsd": payg_payment_threshold_usd(team.plan),
        "members": per_user,
        **(free_extension_summary(user) if user is not None else {}),
    }


def preflight_usage(db: Session, team: BillingTeam, user: ExtUser) -> dict:
    """Check whether a new request may start (does not increment usage)."""
    start_ms, _ = current_period_bounds()
    team_used = team_period_requests(db, team.id, start_ms)
    team_lines = team_period_lines(db, team.id, start_ms)
    credit = db.scalar(select(CreditBalance.balance_usd).where(CreditBalance.team_id == team.id))
    return can_start_new_request(
        plan_id=team.plan,
        payg_enabled=team.payg_enabled,
        team_requests=team_used,
        team_lines=team_lines,
        credit_balance_usd=round(float(credit or 0.0), 2),
        free_extension_claimed=bool(user.free_extension_claimed),
        bonus_requests=int(user.free_extension_requests or 0),
        bonus_lines=int(user.free_extension_line_edits or 0),
    )


def record_usage(
    db: Session,
    team: BillingTeam,
    user: ExtUser,
    requests: int,
    tokens: int,
    line_edits: int = 0,
) -> dict:
    """Increment usage. Always records; gating applies to the *next* request only."""
    start_ms, _ = current_period_bounds()
    plan = get_plan(team.plan)
    credit = db.scalar(select(CreditBalance.balance_usd).where(CreditBalance.team_id == team.id))
    credit_usd = round(float(credit or 0.0), 2)

    team_used_before = team_period_requests(db, team.id, start_ms)
    team_lines_before = team_period_lines(db, team.id, start_ms)
    before = can_start_new_request(
        plan_id=team.plan,
        payg_enabled=team.payg_enabled,
        team_requests=team_used_before,
        team_lines=team_lines_before,
        credit_balance_usd=credit_usd,
        free_extension_claimed=bool(user.free_extension_claimed),
        bonus_requests=int(user.free_extension_requests or 0),
        bonus_lines=int(user.free_extension_line_edits or 0),
    )

    user_rec = _period_record(db, team.id, user.id, start_ms)
    user_rec.requests += max(0, requests)
    user_rec.line_edits += max(0, line_edits)
    user_rec.tokens += max(0, tokens)
    user_rec.updated_at_ms = ms_now()

    # Bonus pool: attribute overage to free-extension counters when monthly included is full.
    bill_before = _overage_billing(team.plan, team_used_before, team_lines_before)
    if (bill_before["lineExhausted"] or bill_before["reqExhausted"]) and user.free_extension_claimed:
        if not plan.payg_allowed or not team.payg_enabled:
            user.free_extension_requests = int(user.free_extension_requests or 0) + max(0, requests)
            user.free_extension_line_edits = int(user.free_extension_line_edits or 0) + max(0, line_edits)

    team_used = team_period_requests(db, team.id, start_ms)
    team_lines = team_period_lines(db, team.id, start_ms)
    bill = _overage_billing(team.plan, team_used, team_lines)

    nxt = next_plan(team.plan)
    gap = payg_gap_usd(team.plan)

    decision = {
        "allowed": True,
        "needsPayment": False,
        "reason": "ok",
        "limitReason": None,
        "teamRequests": team_used,
        "teamLines": team_lines,
        "quota": plan.request_quota,
        "lineQuota": plan.line_quota,
        "overageUnits": bill["reqOver"],
        "lineOverageUnits": bill["lineOver"],
        "requestBillUsd": bill["reqBillUsd"],
        "lineBillUsd": bill["lineBillUsd"],
        "overageUsd": bill["billUsd"],
        "nextPlan": nxt.id if nxt else None,
        "upgradeGapUsd": gap,
        "paygThresholdUsd": payg_payment_threshold_usd(team.plan),
        "creditBalanceUsd": credit_usd,
    }

    if plan.payg_allowed and team.payg_enabled and bill["billUsd"] > 0:
        spent = spend_credit(
            db,
            team_id=team.id,
            amount_usd=bill["billUsd"],
            reason="payg_auto",
            user_id=user.id,
        )
        uncovered = round(max(0.0, bill["billUsd"] - spent), 2)
        team.payg_due_usd = uncovered
        decision["paygUncoveredUsd"] = uncovered
        decision["creditBalanceUsd"] = round(credit_usd - spent, 2)
        credit_usd = decision["creditBalanceUsd"]

    after = can_start_new_request(
        plan_id=team.plan,
        payg_enabled=team.payg_enabled,
        team_requests=team_used,
        team_lines=team_lines,
        credit_balance_usd=credit_usd,
        free_extension_claimed=bool(user.free_extension_claimed),
        bonus_requests=int(user.free_extension_requests or 0),
        bonus_lines=int(user.free_extension_line_edits or 0),
    )
    decision.update(evaluate_after_usage(before, after))
    decision["limitReason"] = after.get("limitReason")
    decision["needsPayment"] = after.get("needsPayment", False)
    decision["reason"] = after.get("reason", "ok")
    if user is not None:
        decision.update(free_extension_summary(user))
    db.commit()
    return decision


def open_payg_charge(db: Session, team: BillingTeam) -> PaygCharge:
    start_ms, _ = current_period_bounds()
    team_used = team_period_requests(db, team.id, start_ms)
    team_lines = team_period_lines(db, team.id, start_ms)
    bill = _overage_billing(team.plan, team_used, team_lines)
    charge = PaygCharge(
        team_id=team.id,
        units=bill["reqOver"],
        line_units=bill["lineOver"],
        amount_usd=bill["billUsd"],
        status="pending",
    )
    db.add(charge)
    db.commit()
    db.refresh(charge)
    return charge
