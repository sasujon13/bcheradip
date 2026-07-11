"""Cheradip extension LLM keys — extcheradip.ext_provider_keys (+ .env fallback)."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.ext_database import ExtSessionLocal
from app.models import ExtProviderKey

# Extension provider id -> Settings attribute (same env vars as ailt_api LLM_KEYS.md)
_PROVIDER_ENV: dict[str, str] = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google": "gemini_api_key",
    "groq": "groq_api_key",
    "mistral": "mistral_api_key",
    "deepseek": "deepseek_api_key",
}

EXTENSION_PROVIDER_IDS = tuple(_PROVIDER_ENV.keys())


def _env_key(provider_id: str) -> str:
    attr = _PROVIDER_ENV.get(provider_id)
    if not attr:
        return ""
    return (getattr(settings, attr, "") or "").strip()


def seed_ext_provider_keys(db: Session) -> int:
    """Upsert keys from .env when the DB row is missing or empty."""
    now_ms = int(time.time() * 1000)
    seeded = 0
    for provider_id in EXTENSION_PROVIDER_IDS:
        env_val = _env_key(provider_id)
        if not env_val:
            continue
        row = db.get(ExtProviderKey, provider_id)
        if row and row.api_key.strip():
            continue
        if row:
            row.api_key = env_val
            row.updated_at_ms = now_ms
        else:
            db.add(ExtProviderKey(provider_id=provider_id, api_key=env_val, updated_at_ms=now_ms))
        seeded += 1
    return seeded


def get_provider_key(db: Session, provider_id: str) -> str:
    row = db.get(ExtProviderKey, provider_id)
    if row and row.api_key.strip():
        return row.api_key.strip()
    return _env_key(provider_id)


def list_provider_keys_for_client(db: Session) -> dict[str, str]:
    """Return only configured keys for authenticated extension clients."""
    out: dict[str, str] = {}
    for provider_id in EXTENSION_PROVIDER_IDS:
        key = get_provider_key(db, provider_id)
        if key:
            out[provider_id] = key
    return out


def mask_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "••••" if k else ""
    return k[:4] + "…" + k[-4:]


def list_provider_key_status(db: Session) -> list[dict]:
    rows: list[dict] = []
    for provider_id in EXTENSION_PROVIDER_IDS:
        key = get_provider_key(db, provider_id)
        rows.append(
            {
                "providerId": provider_id,
                "configured": bool(key),
                "keyHint": mask_key(key),
            }
        )
    return rows


def set_provider_key(db: Session, provider_id: str, api_key: str | None) -> None:
    if provider_id not in _PROVIDER_ENV:
        raise ValueError(f"Unknown provider: {provider_id}")
    now_ms = int(time.time() * 1000)
    row = db.get(ExtProviderKey, provider_id)
    if api_key is None or not api_key.strip():
        if row:
            db.delete(row)
        return
    val = api_key.strip()
    if row:
        row.api_key = val
        row.updated_at_ms = now_ms
    else:
        db.add(ExtProviderKey(provider_id=provider_id, api_key=val, updated_at_ms=now_ms))


def invalidate_cache() -> None:
    pass  # reserved if we add in-process caching later
