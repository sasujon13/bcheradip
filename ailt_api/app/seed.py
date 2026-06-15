"""Create tables and seed admin, promos, languages, AI providers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.schema_upgrade import upgrade_schema
from app.models import (
    AiProvider,
    AiRoutingPolicy,
    LanguagePack,
    PromoCode,
    ReferralPolicy,
    User,
)
from app.security import hash_password
from app.services.pack_store import sync_packs_to_db

logger = logging.getLogger(__name__)
AILT_ROOT = Path(__file__).resolve().parents[1]
PROMO_FILE = AILT_ROOT / "promo-codes.example.json"
AI_PROVIDERS_FILE = AILT_ROOT / "ai-providers.example.json"


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def seed_if_empty(db: Session) -> None:
    _seed_admin(db)
    _seed_promos(db)
    _seed_referral_policy(db)
    _seed_ai_providers(db)
    db.commit()
    sync_packs_to_db(db)


def _seed_admin(db: Session) -> None:
    email = settings.admin_seed_email
    existing = db.scalar(select(User).where(User.email == email))
    password = settings.admin_seed_password
    if not password:
        logger.warning("ADMIN_SEED_PASSWORD not set — admin user not created")
        return
    if existing:
        existing.password_hash = hash_password(password)
        existing.role = "admin"
        existing.whatsapp = settings.admin_seed_whatsapp
        existing.email_verified = True
        existing.whatsapp_verified = True
        return
    db.add(
        User(
            email=email,
            whatsapp=settings.admin_seed_whatsapp,
            username=email.split("@")[0],
            password_hash=hash_password(password),
            role="admin",
            full_name="Admin",
            email_verified=True,
            whatsapp_verified=True,
            login_with="email",
        )
    )
    logger.info("Seeded admin user %s", email)


def _seed_promos(db: Session) -> None:
    if not PROMO_FILE.is_file():
        return
    data = json.loads(PROMO_FILE.read_text(encoding="utf-8"))
    existing = {p.code for p in db.scalars(select(PromoCode)).all()}
    for p in data.get("promoCodes", []):
        code = p["code"].upper()
        if code in existing:
            continue
        db.add(
            PromoCode(
                code=code,
                discount_percent=int(p.get("discountPercent", 0)),
                active=bool(p.get("active", True)),
                auto_apply=bool(p.get("autoApplyForAll", False)),
                paywall_slot=int(p.get("paywallSlot", 2)),
            )
        )
    db.commit()


def _seed_referral_policy(db: Session) -> None:
    if db.scalar(select(ReferralPolicy).limit(1)):
        return
    pol = {}
    if PROMO_FILE.is_file():
        pol = json.loads(PROMO_FILE.read_text(encoding="utf-8")).get("referralPolicy", {})
    db.add(
        ReferralPolicy(
            active=bool(pol.get("active", True)),
            buyer_discount_percent=int(pol.get("referrerBuyerDiscountPercent", 20)),
            commission_percent=int(pol.get("commissionPercent", 20)),
            notice_text="Refer friends and earn commission on their subscriptions.",
        )
    )


def _seed_languages(db: Session) -> None:
    """Deprecated — use sync_packs_to_db from pack_store."""
    sync_packs_to_db(db)


def _seed_ai_providers(db: Session) -> None:
    if not AI_PROVIDERS_FILE.is_file():
        return
    data = json.loads(AI_PROVIDERS_FILE.read_text(encoding="utf-8"))
    routing = data.get("routing_policy", {})
    if not db.scalar(select(AiRoutingPolicy).limit(1)):
        db.add(
            AiRoutingPolicy(
                mode=routing.get("mode", "random_free"),
                prefer_paid_when_free_exhausted=bool(routing.get("prefer_paid_when_free_exhausted", True)),
            )
        )
    existing_ids = {
        p.id for p in db.scalars(select(AiProvider)).all()
    }
    for p in data.get("providers", []):
        if p["id"] in existing_ids:
            continue
        db.add(
            AiProvider(
                id=p["id"],
                display_name=p["display_name"],
                tier=p.get("tier", "free"),
                enabled=bool(p.get("enabled", True)),
                quota_daily_limit=p.get("daily_quota"),
            )
        )


def init_database() -> None:
    create_tables()
    upgrade_schema(engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
