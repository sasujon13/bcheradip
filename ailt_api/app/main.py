"""Cheradip AILT API — MySQL-backed (XAMPP)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.middleware.translate_response import TranslateResponseMiddleware
from app.routers import admin, ai, auth, billing, device, languages, learning, promo, referral
from app.seed import init_database
from app.services.pack_store import list_available_codes
from app.services.email_templates import OTP_TEMPLATE_VERSION

_EMAIL_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "email"

logger = logging.getLogger(__name__)

_LOCAL_POSTFIX_MSG = (
    "SMTP 127.0.0.1:25 is not used — configure Brevo: deploy/BREVO_EMAIL.md"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        init_database()
        logger.info("Database ready: ailanguagetutor")
        if settings.smtp_enabled and settings.uses_local_postfix_direct():
            logger.error(_LOCAL_POSTFIX_MSG)
        elif settings.smtp_enabled:
            logger.info("SMTP: %s (template %s)", settings.smtp_config_summary(), OTP_TEMPLATE_VERSION)
    except Exception as e:
        logger.error("Database startup failed: %s", e)
        raise
    yield


app = FastAPI(title="Cheradip AILT API", version="1.0.0", lifespan=lifespan)
app.add_middleware(TranslateResponseMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = FastAPI()
app.mount("/api/ailt", api)

api.include_router(auth.router)
api.include_router(device.router)
api.include_router(billing.router)
api.include_router(promo.router)
api.include_router(referral.router)
api.include_router(languages.router)
api.include_router(admin.router)
api.include_router(ai.router)
api.include_router(learning.router)

if _EMAIL_ASSETS_DIR.is_dir():
    api.mount("/assets/email", StaticFiles(directory=_EMAIL_ASSETS_DIR), name="email_assets")


@api.get("/health")
def health() -> dict:
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "cheradip-ailt-api",
        "database": "ailanguagetutor" if db_ok else "unavailable",
        "language_packs_available": len(list_available_codes()),
        "llm_keys_configured": bool(
            settings.gemini_api_key
            or settings.openai_api_key
            or settings.groq_api_key
            or settings.anthropic_api_key
            or settings.mistral_api_key
            or settings.openrouter_api_key
        ),
        "smtp_enabled": settings.smtp_enabled,
        "smtp_configured": bool(settings.smtp_host and settings.smtp_from),
        "email_template": OTP_TEMPLATE_VERSION,
        "email_assets_base_url": settings.resolved_email_assets_base_url(),
    }
