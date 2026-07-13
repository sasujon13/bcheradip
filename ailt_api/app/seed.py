"""Create tables and seed admin, promos, languages, AI providers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.ext_database import ExtBase, ExtSessionLocal, ext_engine
from app.schema_upgrade import upgrade_schema
from app.models import (
    AiProvider,
    AiRoutingPolicy,
    ExtUser,
    LanguagePack,
    PromoCode,
    ReferralPolicy,
    User,
)
from app.security import hash_password
from app.services.ext_provider_keys import seed_ext_provider_keys
from app.services.pack_store import sync_packs_to_db

logger = logging.getLogger(__name__)
AILT_ROOT = Path(__file__).resolve().parents[1]
PROMO_FILE = AILT_ROOT / "promo-codes.example.json"
AI_PROVIDERS_FILE = AILT_ROOT / "ai-providers.example.json"


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


_EXT_TABLES = (
    "credit_transactions",
    "credit_balances",
    "ext_payments",
    "payg_charges",
    "usage_records",
    "team_members",
    "billing_teams",
    "ext_sessions",
    "ext_otp_codes",
    "ext_users",
)


def _drop_legacy_ext_tables_from_main() -> None:
    """Extension tables now live in the ``extcheradip`` database.

    Older builds created them inside ``ailanguagetutor``. If any remain in the
    main DB, drop them (dev-only, empty) so there is a single source of truth.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    present = [t for t in _EXT_TABLES if insp.has_table(t)]
    if not present:
        return
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in present:
            conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    logger.info("Dropped %d legacy extension tables from main DB (moved to extcheradip)", len(present))


def seed_if_empty(db: Session) -> None:
    _seed_admin(db)
    _seed_promos(db)
    _seed_referral_policy(db)
    _seed_ai_providers(db)
    db.commit()


def _seed_ext_admin(db: Session) -> None:
    """Seed the Cheradip extension admin account (separate ext_users space)."""
    email = (settings.ext_admin_seed_email or settings.admin_seed_email).strip().lower()
    password = settings.ext_admin_seed_password or settings.admin_seed_password
    if not password:
        logger.warning("No ext admin password (ext_admin_seed_password/admin_seed_password) — ext admin not created")
        return
    existing = db.scalar(select(ExtUser).where(ExtUser.email == email))
    if existing:
        existing.password_hash = hash_password(password)
        existing.role = "admin"
        existing.email_verified = True
        existing.active = True
        return
    db.add(
        ExtUser(
            email=email,
            username=email.split("@")[0],
            password_hash=hash_password(password),
            role="admin",
            full_name="Cheradip Admin",
            email_verified=True,
            active=True,
        )
    )
    logger.info("Seeded ext admin user %s", email)


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
                quota_daily_limit=None,
            )
        )


def init_database() -> None:
    _drop_legacy_ext_tables_from_main()
    create_tables()
    upgrade_schema(engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
        # Refresh language_packs.download_url from disk on every startup (PUBLIC_BASE_URL changes).
        sync_packs_to_db(db)
    finally:
        db.close()


def init_ext_database() -> None:
    """Create + seed the Cheradip extension database (extcheradip)."""
    ExtBase.metadata.create_all(bind=ext_engine)
    # Idempotent ALTER TABLE patches (e.g. usage_records.line_edits). The patch
    # list is shared with the main DB; non-existent tables are skipped safely.
    upgrade_schema(ext_engine)
    db = ExtSessionLocal()
    try:
        _seed_ext_admin(db)
        n = seed_ext_provider_keys(db)
        if n:
            logger.info("Seeded %d ext_provider_keys from .env", n)
        db.commit()
    finally:
        db.close()
