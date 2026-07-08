"""Runtime, admin-editable settings — DB (``app_settings``) overrides ``.env``.

Used for Paddle payment credentials so an admin can set them from the web admin
page (``/ailt/paddle``) without a redeploy. Values are cached in-process and the
cache is invalidated on write.

Secrets (API key, webhook secret) are only ever read server-side. The publishable
client token + price ids may be surfaced to the pricing page.
"""

from __future__ import annotations

import time

from sqlalchemy import select

from app.config import settings
from app.ext_database import ExtSessionLocal
from app.models import AppSetting

# setting key -> the Settings attribute used as fallback when the DB has no value
_ENV_FALLBACK: dict[str, str] = {
    "paddle_environment": "paddle_environment",
    "paddle_api_key": "paddle_api_key",
    "paddle_webhook_secret": "paddle_webhook_secret",
    "paddle_client_token": "paddle_client_token",
    "paddle_price_pro": "paddle_price_pro",
    "paddle_price_plus": "paddle_price_plus",
    "paddle_price_business": "paddle_price_business",
}

PADDLE_KEYS = tuple(_ENV_FALLBACK.keys())

# Cache DB values briefly so config changes from the admin page propagate to all
# gunicorn workers within this window (each worker has its own cache) without a
# DB read on every request.
_CACHE_TTL_S = 30.0

_cache: dict[str, str] | None = None
_cache_at: float = 0.0


def _load() -> dict[str, str]:
    global _cache, _cache_at
    db = ExtSessionLocal()
    try:
        rows = db.scalars(select(AppSetting)).all()
        _cache = {r.key: r.value for r in rows if r.value is not None}
    except Exception:
        # If the ext DB is unavailable, fall back to env only (don't crash callers).
        _cache = {}
    finally:
        db.close()
    _cache_at = time.monotonic()
    return _cache


def invalidate() -> None:
    global _cache
    _cache = None


def get(key: str, default: str = "") -> str:
    """Effective value: DB override, else the matching .env setting, else default."""
    global _cache
    if _cache is None or (time.monotonic() - _cache_at) > _CACHE_TTL_S:
        _load()
    val = (_cache or {}).get(key)
    if val:
        return val
    env_attr = _ENV_FALLBACK.get(key)
    if env_attr:
        env_val = getattr(settings, env_attr, "") or ""
        if env_val:
            return env_val
    return default


def set_many(values: dict[str, str | None]) -> None:
    """Upsert settings. ``None`` leaves an existing value untouched; ""/blank clears it."""
    now_ms = int(time.time() * 1000)
    db = ExtSessionLocal()
    try:
        for key, value in values.items():
            if value is None:
                continue
            row = db.get(AppSetting, key)
            if row:
                row.value = value
                row.updated_at_ms = now_ms
            else:
                db.add(AppSetting(key=key, value=value, updated_at_ms=now_ms))
        db.commit()
    finally:
        db.close()
    invalidate()
