"""Admin console API for the Cheradip extension — accounts, teams/plans,
credit balances, and payment history. Server-only (ext admin role)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ext_database import get_ext_db
from app.deps import require_ext_admin
from app.models import (
    BillingTeam,
    CreditTransaction,
    ExtPayment,
    ExtUser,
    TeamMember,
)
from app.schemas import (
    ExtAdminCreditGrantRequest,
    ExtAdminPlanUpdateRequest,
    ExtAdminUserUpdateRequest,
)
from app.services.credits import get_or_create_balance, grant_credit
from app.services.plans import current_period_bounds, get_plan
from app.services.team_billing import team_period_requests, usage_summary

router = APIRouter(prefix="/ext/admin", tags=["ext-admin"])


@router.get("/overview")
def overview(
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
) -> dict:
    total_users = db.scalar(select(func.count(ExtUser.id))) or 0
    total_teams = db.scalar(select(func.count(BillingTeam.id))) or 0
    paid_teams = db.scalar(
        select(func.count(BillingTeam.id)).where(BillingTeam.plan != "free")
    ) or 0
    revenue = db.scalar(
        select(func.coalesce(func.sum(ExtPayment.amount_usd), 0.0)).where(
            ExtPayment.status == "paid"
        )
    ) or 0.0
    return {
        "users": int(total_users),
        "teams": int(total_teams),
        "paidTeams": int(paid_teams),
        "lifetimeRevenueUsd": round(float(revenue), 2),
    }


@router.get("/users")
def list_users(
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(ExtUser).order_by(ExtUser.id.desc())
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where((ExtUser.email.like(like)) | (ExtUser.username.like(like)))
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    out = []
    for u in rows:
        member = db.scalar(select(TeamMember).where(TeamMember.user_id == u.id).limit(1))
        team = db.get(BillingTeam, member.team_id) if member else None
        out.append(
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "fullName": u.full_name,
                "role": u.role,
                "active": u.active,
                "lastLoginAtMs": u.last_login_at_ms,
                "teamId": team.id if team else None,
                "plan": team.plan if team else None,
            }
        )
    return {"users": out}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    body: ExtAdminUserUpdateRequest,
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
) -> dict:
    user = db.get(ExtUser, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if body.role is not None:
        if body.role not in ("user", "admin"):
            raise HTTPException(400, "role must be user or admin")
        user.role = body.role
    if body.active is not None:
        user.active = body.active
    db.commit()
    return {"ok": True, "id": user.id, "role": user.role, "active": user.active}


@router.get("/teams")
def list_teams(
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    rows = db.scalars(
        select(BillingTeam).order_by(BillingTeam.id.desc()).limit(limit).offset(offset)
    ).all()
    start_ms, _ = current_period_bounds()
    out = []
    for t in rows:
        owner = db.get(ExtUser, t.owner_user_id)
        seats_used = db.scalar(
            select(func.count(TeamMember.id)).where(TeamMember.team_id == t.id)
        ) or 0
        bal = get_or_create_balance(db, t.id)
        out.append(
            {
                "id": t.id,
                "name": t.name,
                "ownerEmail": owner.email if owner else None,
                "plan": t.plan,
                "status": t.status,
                "paygEnabled": t.payg_enabled,
                "seats": t.seats,
                "seatsUsed": int(seats_used),
                "licenseKey": t.license_key,
                "periodRequests": team_period_requests(db, t.id, start_ms),
                "quota": get_plan(t.plan).request_quota,
                "paygDueUsd": round(t.payg_due_usd, 2),
                "creditBalanceUsd": round(bal.balance_usd, 2),
            }
        )
    db.commit()
    return {"teams": out}


@router.get("/teams/{team_id}")
def team_detail(
    team_id: int,
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
) -> dict:
    team = db.get(BillingTeam, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return usage_summary(db, team, None)


@router.patch("/teams/{team_id}/plan")
def update_team_plan(
    team_id: int,
    body: ExtAdminPlanUpdateRequest,
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
) -> dict:
    team = db.get(BillingTeam, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    team.plan = get_plan(body.plan).id
    if body.paygEnabled is not None:
        team.payg_enabled = body.paygEnabled
    if body.status is not None:
        if body.status not in ("active", "past_due", "canceled"):
            raise HTTPException(400, "invalid status")
        team.status = body.status
    db.commit()
    return {"ok": True, "teamId": team.id, "plan": team.plan, "status": team.status}


@router.post("/credits/grant")
def credits_grant(
    body: ExtAdminCreditGrantRequest,
    admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
) -> dict:
    team = db.get(BillingTeam, body.teamId)
    if not team:
        raise HTTPException(404, "Team not found")
    bal = grant_credit(
        db,
        team_id=team.id,
        amount_usd=body.amountUsd,
        reason=body.reason or "admin_grant",
        actor_user_id=admin.id,
    )
    return {"ok": True, "teamId": team.id, "balanceUsd": round(bal.balance_usd, 2)}


@router.get("/credits/{team_id}")
def credits_history(
    team_id: int,
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
    limit: int = Query(default=100, le=500),
) -> dict:
    bal = get_or_create_balance(db, team_id)
    db.commit()
    rows = db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.team_id == team_id)
        .order_by(CreditTransaction.id.desc())
        .limit(limit)
    ).all()
    txns = [
        {
            "id": t.id,
            "deltaUsd": t.delta_usd,
            "reason": t.reason,
            "balanceAfterUsd": t.balance_after_usd,
            "userId": t.user_id,
            "createdAtMs": t.created_at_ms,
        }
        for t in rows
    ]
    return {"teamId": team_id, "balanceUsd": round(bal.balance_usd, 2), "transactions": txns}


@router.get("/payments")
def list_payments(
    _admin: ExtUser = Depends(require_ext_admin),
    db: Session = Depends(get_ext_db),
    team_id: int | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    stmt = select(ExtPayment).order_by(ExtPayment.id.desc())
    if team_id is not None:
        stmt = stmt.where(ExtPayment.team_id == team_id)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    payments = [
        {
            "id": p.id,
            "teamId": p.team_id,
            "userId": p.user_id,
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
    return {"payments": payments}
