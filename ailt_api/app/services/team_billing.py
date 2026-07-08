"""Team resolution, usage aggregation, and PAYG evaluation for the extension."""

from __future__ import annotations

import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BillingTeam, CreditBalance, ExtUser, PaygCharge, TeamMember, UsageRecord
from app.services.plans import (
    PAYG_UNIT_USD,
    current_period_bounds,
    get_plan,
    ms_now,
    next_plan,
    payg_gap_usd,
)


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


def usage_summary(db: Session, team: BillingTeam, user: ExtUser | None) -> dict:
    start_ms, end_ms = current_period_bounds()
    plan = get_plan(team.plan)
    team_used = team_period_requests(db, team.id, start_ms)

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
                "tokens": r.tokens,
            }
        )

    overage = max(0, team_used - plan.request_quota)
    overage_usd = round(overage * PAYG_UNIT_USD, 2)
    gap = payg_gap_usd(team.plan)
    nxt = next_plan(team.plan)
    credit = db.scalar(select(CreditBalance.balance_usd).where(CreditBalance.team_id == team.id))
    credit_usd = round(float(credit or 0.0), 2)

    my_requests = 0
    if user is not None:
        mine = db.scalar(
            select(UsageRecord.requests).where(
                UsageRecord.team_id == team.id,
                UsageRecord.period_start_ms == start_ms,
                UsageRecord.user_id == user.id,
            )
        )
        my_requests = int(mine or 0)

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
        "teamRequests": team_used,
        "myRequests": my_requests,
        "overageUnits": overage,
        "overageUsd": overage_usd,
        "paygDueUsd": round(team.payg_due_usd, 2),
        "paygUnitUsd": PAYG_UNIT_USD,
        "creditBalanceUsd": credit_usd,
        "nextPlan": nxt.id if nxt else None,
        "nextPlanPriceUsd": nxt.price_usd if nxt else None,
        "upgradeGapUsd": gap,
        "members": per_user,
    }


def record_usage(db: Session, team: BillingTeam, user: ExtUser, requests: int, tokens: int) -> dict:
    """Increment usage and evaluate quota / PAYG gating.

    Returns a decision dict:
      allowed        — request is permitted
      needsPayment   — client must pay PAYG now or upgrade
      reason         — quota_exceeded | payg_threshold | ok
    """
    start_ms, _ = current_period_bounds()
    plan = get_plan(team.plan)

    user_rec = _period_record(db, team.id, user.id, start_ms)
    user_rec.requests += max(0, requests)
    user_rec.tokens += max(0, tokens)
    user_rec.updated_at_ms = ms_now()

    team_used = team_period_requests(db, team.id, start_ms)
    overage = max(0, team_used - plan.request_quota)
    overage_usd = round(overage * PAYG_UNIT_USD, 2)

    decision = {
        "allowed": True,
        "needsPayment": False,
        "reason": "ok",
        "teamRequests": team_used,
        "quota": plan.request_quota,
        "overageUnits": overage,
        "overageUsd": overage_usd,
        "nextPlan": None,
        "upgradeGapUsd": None,
    }

    if team_used <= plan.request_quota:
        db.commit()
        return decision

    nxt = next_plan(team.plan)
    gap = payg_gap_usd(team.plan)
    decision["nextPlan"] = nxt.id if nxt else None
    decision["upgradeGapUsd"] = gap

    # Free plan (or PAYG disabled): hard stop once quota is used up.
    if not plan.payg_allowed or not team.payg_enabled:
        decision["allowed"] = False
        decision["needsPayment"] = True
        decision["reason"] = "quota_exceeded"
        db.commit()
        return decision

    # PAYG on: accumulate overage as amount due; prompt when we hit the next-tier gap.
    team.payg_due_usd = overage_usd
    if gap is not None and overage_usd >= gap:
        decision["needsPayment"] = True
        decision["reason"] = "payg_threshold"
    db.commit()
    return decision


def open_payg_charge(db: Session, team: BillingTeam) -> PaygCharge:
    start_ms, _ = current_period_bounds()
    plan = get_plan(team.plan)
    team_used = team_period_requests(db, team.id, start_ms)
    overage = max(0, team_used - plan.request_quota)
    amount = round(overage * PAYG_UNIT_USD, 2)
    charge = PaygCharge(
        team_id=team.id,
        units=overage,
        amount_usd=amount,
        status="pending",
    )
    db.add(charge)
    db.commit()
    db.refresh(charge)
    return charge
