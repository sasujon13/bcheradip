from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import (
    AdminReportSettings,
    AiProvider,
    AiRoutingPolicy,
    DeviceTrial,
    LanguagePack,
    PromoCode,
    ReferralBalance,
    ReferralPolicy,
    ReferralWithdrawal,
    Subscription,
    User,
    UserLearningActivity,
)
from app.schemas import AdminPromoCodeDto, AdminPromoPatchDto, AiProviderToggleRequest, AiRoutingPolicyUpdateRequest, ReferralPolicyPatchDto
from app.security import quota_used_percent
from app.services.earnings_report import build_earnings_report
from app.services.referral_earnings import mature_pending_earnings

router = APIRouter(prefix="/admin", tags=["admin"])


def _report_settings(db: Session) -> AdminReportSettings:
    row = db.scalar(select(AdminReportSettings).limit(1))
    if row is None:
        row = AdminReportSettings()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _effective_health(provider: AiProvider) -> str:
    if provider.health in ("disabled", "exhausted"):
        return provider.health
    if provider.last_error:
        return "degraded"
    return provider.health or "healthy"


def _promo_to_dict(row: PromoCode) -> dict:
    return {
        "code": row.code,
        "discount_percent": row.discount_percent,
        "active": row.active,
        "auto_apply": row.auto_apply,
        "paywall_slot": row.paywall_slot,
    }


@router.get("/promo-codes")
def list_promo_codes(db: Session = Depends(get_db)) -> dict:
    """All rows from promo_codes table (admin console source of truth)."""
    rows = db.scalars(select(PromoCode).order_by(PromoCode.paywall_slot, PromoCode.code)).all()
    return {"codes": [_promo_to_dict(r) for r in rows]}


@router.post("/promo-codes")
def create_promo_code(body: AdminPromoCodeDto, db: Session = Depends(get_db)) -> dict:
    code = body.code.upper().strip()
    if not code:
        raise HTTPException(400, "Promo code is required")
    if db.scalar(select(PromoCode).where(PromoCode.code == code)):
        raise HTTPException(409, "Promo code already exists")
    row = PromoCode(
        code=code,
        discount_percent=max(0, min(body.discount_percent, 100)),
        active=body.active,
        auto_apply=body.auto_apply,
        paywall_slot=body.paywall_slot,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _promo_to_dict(row)


@router.patch("/promo-codes/{code}")
def patch_promo_code(code: str, body: AdminPromoPatchDto, db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(PromoCode).where(PromoCode.code == code.upper()))
    if not row:
        raise HTTPException(404, "Promo not found")
    if body.discount_percent is not None:
        row.discount_percent = max(0, min(body.discount_percent, 100))
        if body.discount_percent == 0:
            row.active = False
    if body.active is not None:
        row.active = body.active
    if body.auto_apply is not None:
        row.auto_apply = body.auto_apply
    if body.paywall_slot is not None:
        row.paywall_slot = body.paywall_slot
    db.commit()
    db.refresh(row)
    return _promo_to_dict(row)


@router.patch("/referral-policy")
def patch_referral_policy(body: ReferralPolicyPatchDto, db: Session = Depends(get_db)) -> dict:
    pol = db.scalar(select(ReferralPolicy).limit(1))
    if not pol:
        pol = ReferralPolicy()
        db.add(pol)
    if body.active is not None:
        pol.active = body.active
    if body.buyer_discount_percent is not None:
        pol.buyer_discount_percent = body.buyer_discount_percent
    if body.commission_percent is not None:
        pol.commission_percent = body.commission_percent
    if body.notice_text is not None:
        pol.notice_text = body.notice_text
    db.commit()
    return {
        "active": pol.active,
        "buyer_discount_percent": pol.buyer_discount_percent,
        "commission_percent": pol.commission_percent,
        "notice_text": pol.notice_text,
    }


@router.get("/ai/providers")
def ai_providers(db: Session = Depends(get_db)) -> dict:
    providers = db.scalars(select(AiProvider)).all()
    routing = db.scalar(select(AiRoutingPolicy).limit(1))
    mode = routing.mode if routing else "random_free"
    prefer_paid = routing.prefer_paid_when_free_exhausted if routing else True
    dto_list = []
    total = 0
    free_ok = False
    exhausted = 0
    for p in providers:
        total += p.requests_today
        pct = quota_used_percent(p.requests_today, p.quota_daily_limit)
        health = _effective_health(p)
        if p.tier == "free" and p.enabled and health == "healthy":
            free_ok = True
        if health == "exhausted":
            exhausted += 1
        dto_list.append(
            {
                "id": p.id,
                "display_name": p.display_name,
                "tier": p.tier,
                "health": health,
                "quota_used_percent": pct,
                "requests_today": p.requests_today,
                "quota_daily_limit": p.quota_daily_limit,
                "last_error": p.last_error,
                "last_used_at": p.last_used_at_ms,
                "enabled": p.enabled,
            }
        )
    summary = f"{mode}: {len([x for x in providers if x.enabled])} providers configured."
    return {
        "providers": dto_list,
        "routing_policy": {"mode": mode, "prefer_paid_when_free_exhausted": prefer_paid},
        "total_requests_today": total,
        "free_pool_available": free_ok,
        "recommend_paid_upgrade": exhausted > 0 and not free_ok,
        "summary": summary,
    }


@router.patch("/ai/routing")
def update_ai_routing(body: AiRoutingPolicyUpdateRequest, db: Session = Depends(get_db)) -> dict:
    routing = db.scalar(select(AiRoutingPolicy).limit(1))
    if not routing:
        routing = AiRoutingPolicy()
        db.add(routing)
    routing.mode = body.mode
    if body.prefer_paid_when_free_exhausted is not None:
        routing.prefer_paid_when_free_exhausted = body.prefer_paid_when_free_exhausted
    db.commit()
    return {
        "mode": routing.mode,
        "prefer_paid_when_free_exhausted": routing.prefer_paid_when_free_exhausted,
    }


@router.patch("/ai/providers/{provider_id}")
def toggle_ai_provider(provider_id: str, body: AiProviderToggleRequest, db: Session = Depends(get_db)) -> dict:
    p = db.get(AiProvider, provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    p.enabled = body.enabled
    db.commit()
    return {
        "id": p.id,
        "display_name": p.display_name,
        "tier": p.tier,
        "health": p.health,
        "enabled": p.enabled,
    }


@router.get("/reports/settings")
def admin_reports_settings(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    s = _report_settings(db)
    return {
        "cloud_reports_enabled": s.cloud_reports_enabled,
        "home_ai_reports_enabled": s.home_ai_reports_enabled,
        "debug_reports_enabled": s.debug_reports_enabled,
    }


@router.patch("/reports/settings")
def patch_admin_reports_settings(
    body: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    s = _report_settings(db)
    if "cloud_reports_enabled" in body:
        s.cloud_reports_enabled = bool(body["cloud_reports_enabled"])
    if "home_ai_reports_enabled" in body:
        s.home_ai_reports_enabled = bool(body["home_ai_reports_enabled"])
    if "debug_reports_enabled" in body:
        s.debug_reports_enabled = bool(body["debug_reports_enabled"])
    db.commit()
    db.refresh(s)
    return {
        "cloud_reports_enabled": s.cloud_reports_enabled,
        "home_ai_reports_enabled": s.home_ai_reports_enabled,
        "debug_reports_enabled": s.debug_reports_enabled,
    }


@router.get("/reports/debug")
def admin_reports_debug(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    s = _report_settings(db)
    if not s.debug_reports_enabled:
        raise HTTPException(403, "Debug reports are disabled by admin settings.")
    packs = db.scalars(select(LanguagePack).order_by(LanguagePack.code)).all()
    activity_by_lang = db.execute(
        select(UserLearningActivity.language_code, func.count())
        .group_by(UserLearningActivity.language_code)
        .order_by(func.count().desc())
    ).all()
    providers = db.scalars(select(AiProvider)).all()
    return {
        "generated_at_ms": int(datetime.utcnow().timestamp() * 1000),
        "language_packs": [
            {
                "code": p.code,
                "version": p.version,
                "active": p.active,
                "size_bytes": p.size_bytes,
            }
            for p in packs
        ],
        "learning_activity_by_language": [
            {"language_code": row[0], "count": row[1]} for row in activity_by_lang
        ],
        "cloud_ai_provider_errors": [
            {"id": p.id, "last_error": p.last_error, "health": _effective_health(p)}
            for p in providers
            if p.last_error
        ],
    }


@router.get("/reports")
def admin_reports(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Aggregate platform metrics for admin dashboard (requires admin login)."""
    settings = _report_settings(db)
    if not settings.cloud_reports_enabled:
        raise HTTPException(503, "Cloud report generation is disabled by admin settings.")

    now = datetime.utcnow()
    now_ms = int(now.timestamp() * 1000)
    cutoff_7 = now - timedelta(days=7)
    cutoff_30 = now - timedelta(days=30)

    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    admin_users = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    verified_users = db.scalar(
        select(func.count()).select_from(User).where(User.email_verified.is_(True))
    ) or 0
    new_7d = db.scalar(select(func.count()).select_from(User).where(User.created_at >= cutoff_7)) or 0
    new_30d = db.scalar(select(func.count()).select_from(User).where(User.created_at >= cutoff_30)) or 0

    active_subs = db.scalars(
        select(Subscription).where(
            Subscription.active.is_(True),
            (Subscription.expires_at_ms.is_(None)) | (Subscription.expires_at_ms > now_ms),
        )
    ).all()
    active_pro = sum(1 for s in active_subs if (s.tier or "").lower() == "pro")
    active_plus = sum(1 for s in active_subs if (s.tier or "").lower() == "plus")

    learning_activities = db.scalar(select(func.count()).select_from(UserLearningActivity)) or 0
    device_trials = db.scalar(select(func.count()).select_from(DeviceTrial)) or 0
    guest_ai_total = db.scalar(select(func.coalesce(func.sum(DeviceTrial.guest_ai_count), 0))) or 0

    promo_total = db.scalar(select(func.count()).select_from(PromoCode)) or 0
    promo_active = db.scalar(
        select(func.count()).select_from(PromoCode).where(PromoCode.active.is_(True))
    ) or 0

    pending_withdrawals = db.scalar(
        select(func.count()).select_from(ReferralWithdrawal).where(ReferralWithdrawal.status == "pending")
    ) or 0
    mature_pending_earnings(db)
    db.commit()
    referral_balance_total = db.scalar(
        select(func.coalesce(func.sum(ReferralBalance.available_usd), 0.0))
    ) or 0.0
    referral_pending_total = db.scalar(
        select(func.coalesce(func.sum(ReferralBalance.pending_usd), 0.0))
    ) or 0.0

    providers = db.scalars(select(AiProvider)).all()
    cloud_ai_total = sum(p.requests_today for p in providers)
    provider_rows = []
    for p in providers:
        provider_rows.append(
            {
                "id": p.id,
                "display_name": p.display_name,
                "tier": p.tier,
                "health": _effective_health(p),
                "enabled": p.enabled,
                "requests_today": p.requests_today,
                "quota_daily_limit": p.quota_daily_limit,
                "quota_used_percent": quota_used_percent(p.requests_today, p.quota_daily_limit),
            }
        )

    routing = db.scalar(select(AiRoutingPolicy).limit(1))
    routing_mode = routing.mode if routing else "random_free"

    packs = db.scalars(select(LanguagePack).where(LanguagePack.active.is_(True))).all()
    activity_by_lang = db.execute(
        select(UserLearningActivity.language_code, func.count())
        .group_by(UserLearningActivity.language_code)
        .order_by(func.count().desc())
        .limit(12)
    ).all()

    return {
        "generated_at_ms": now_ms,
        "report_settings": {
            "cloud_reports_enabled": settings.cloud_reports_enabled,
            "home_ai_reports_enabled": settings.home_ai_reports_enabled,
            "debug_reports_enabled": settings.debug_reports_enabled,
        },
        "language_packs": {
            "catalog_active": len(packs),
            "packs": [{"code": p.code, "version": p.version, "size_bytes": p.size_bytes} for p in packs],
            "learning_activity_by_language": [
                {"language_code": row[0], "count": row[1]} for row in activity_by_lang
            ],
        },
        "users": {
            "total": total_users,
            "regular": max(0, total_users - admin_users),
            "admins": admin_users,
            "email_verified": verified_users,
            "new_last_7_days": new_7d,
            "new_last_30_days": new_30d,
        },
        "subscriptions": {
            "active_pro": active_pro,
            "active_plus": active_plus,
            "active_total": len(active_subs),
        },
        "engagement": {
            "learning_activities": learning_activities,
            "device_trials": device_trials,
            "guest_ai_uses_total": int(guest_ai_total),
        },
        "referrals": {
            "pending_withdrawals": pending_withdrawals,
            "total_balance_usd": round(float(referral_balance_total), 2),
            "pending_commission_usd": round(float(referral_pending_total), 2),
        },
        "promo_codes": {
            "total": promo_total,
            "active": promo_active,
        },
        "cloud_ai": {
            "routing_mode": routing_mode,
            "total_requests_today": cloud_ai_total,
            "providers": provider_rows,
        },
    }


@router.get("/reports/earnings")
def admin_reports_earnings(
    period: str = "monthly",
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    settings = _report_settings(db)
    if not settings.cloud_reports_enabled:
        raise HTTPException(503, "Cloud report generation is disabled by admin settings.")
    try:
        report = build_earnings_report(db, period=period, from_raw=from_date, to_raw=to_date)
        db.commit()
        return report
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
