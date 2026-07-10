"""Cheradip AILT API — MySQL-backed (XAMPP)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.ext_database import ext_engine
from app.middleware.translate_response import TranslateResponseMiddleware
from app.routers import (
    admin,
    ai,
    auth,
    billing,
    device,
    ext_admin,
    ext_auth,
    ext_project_knowledge,
    languages,
    learning,
    promo,
    referral,
    subscription,
)
from app.seed import init_database, init_ext_database
from app.services.pack_store import list_available_codes
from app.services.email_templates import (
    OTP_TEMPLATE_VERSION,
    _TEMPLATE_PATH,
    logo_path,
    logo_public_url,
)

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
        try:
            with ext_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            init_ext_database()
            logger.info("Database ready: extcheradip (extension)")
        except Exception as ext_err:
            logger.error("Extension database (extcheradip) init failed: %s", ext_err)
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
api.include_router(ext_auth.router)
api.include_router(ext_project_knowledge.router)
api.include_router(ext_admin.router)
api.include_router(subscription.router)
api.include_router(promo.router)
api.include_router(referral.router)
api.include_router(languages.router)
api.include_router(admin.router)
api.include_router(ai.router)
api.include_router(learning.router)


@api.get("/email/cheradip.png", include_in_schema=False)
def email_logo_png() -> FileResponse:
    path = logo_path()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="deploy/cheradip.png not found")
    return FileResponse(path, media_type="image/png", filename="cheradip.png")


@api.get("/health")
def health() -> dict:
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    ext_db_ok = False
    try:
        with ext_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            ext_db_ok = True
    except Exception:
        pass
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "cheradip-ailt-api",
        "database": "ailanguagetutor" if db_ok else "unavailable",
        "ext_database": "extcheradip" if ext_db_ok else "unavailable",
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
        "email_template_file": str(_TEMPLATE_PATH.name),
        "email_template_ok": _TEMPLATE_PATH.is_file(),
        "email_logo_ok": logo_path().is_file(),
        "email_logo_url": logo_public_url(),
    }
