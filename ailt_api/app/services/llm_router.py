"""Pick providers from routing policy, skip failure-exhausted providers, sticky session affinity."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AiProvider, AiRoutingPolicy
from app.security import ms_now
from app.services.ai_session_affinity import get_sticky_provider, set_sticky_provider
from app.services.llm_client import LlmHttpError, generate_text, provider_has_key

logger = logging.getLogger(__name__)

FAILURE_EXHAUST_THRESHOLD = 7


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_daily_quota_reset(db: Session) -> None:
    """Reset per-provider daily stats and failure state at UTC midnight (idempotent per day)."""
    routing = db.scalar(select(AiRoutingPolicy).limit(1))
    if not routing:
        return
    today = _utc_today()
    if routing.quota_reset_day_utc == today:
        return
    routing.quota_reset_day_utc = today
    for provider in db.scalars(select(AiProvider)).all():
        provider.requests_today = 0
        provider.consecutive_failures = 0
        if provider.enabled and provider.health in ("exhausted", "degraded"):
            provider.health = "healthy"
        provider.last_error = None
    db.commit()
    logger.info("AI provider daily stats reset for UTC %s", today)


def _is_eligible(provider: AiProvider) -> bool:
    return provider.enabled and provider.health != "exhausted" and provider.health != "disabled"


def routing_pool(db: Session) -> list[AiProvider]:
    ensure_daily_quota_reset(db)
    routing = db.scalar(select(AiRoutingPolicy).limit(1))
    mode = routing.mode if routing else "random_free"
    providers = db.scalars(select(AiProvider).where(AiProvider.enabled.is_(True))).all()
    if mode == "paid_only":
        pool = [p for p in providers if p.tier == "paid" and _is_eligible(p)]
    elif mode == "random_all":
        pool = [p for p in providers if _is_eligible(p)]
    else:
        pool = [p for p in providers if p.tier == "free" and _is_eligible(p)]
    if not pool and routing and routing.prefer_paid_when_free_exhausted:
        pool = [p for p in providers if p.tier == "paid" and _is_eligible(p)]
    return pool


def _mark_failure(db: Session, provider: AiProvider, message: str, *, status_code: int | None = None) -> None:
    provider.last_error = message[:500]
    provider.consecutive_failures = int(provider.consecutive_failures or 0) + 1
    if provider.consecutive_failures >= FAILURE_EXHAUST_THRESHOLD:
        provider.health = "exhausted"
    elif provider.health not in ("exhausted", "disabled"):
        provider.health = "degraded"
    if status_code == 429:
        provider.last_error = f"HTTP 429 (rate limit): {message[:400]}"
    db.commit()


def _record_success(db: Session, provider: AiProvider) -> str:
    provider.requests_today += 1
    provider.consecutive_failures = 0
    provider.last_used_at_ms = ms_now()
    provider.last_error = None
    if provider.health == "degraded":
        provider.health = "healthy"
    db.commit()
    return provider.id


def _order_candidates(candidates: list[AiProvider], sticky_id: str | None) -> list[AiProvider]:
    if not sticky_id:
        ordered = list(candidates)
        random.shuffle(ordered)
        return ordered
    sticky = [p for p in candidates if p.id == sticky_id]
    rest = [p for p in candidates if p.id != sticky_id]
    random.shuffle(rest)
    return sticky + rest


async def generate_with_fallback(
    db: Session,
    prompt: str,
    *,
    max_tokens: int = 512,
    client_key: str | None = None,
    task_intent: str | None = None,
) -> tuple[str | None, str]:
    """Try eligible providers; prefer last successful provider for this client when still healthy."""
    candidates = [p for p in routing_pool(db) if provider_has_key(p.id)]
    sticky_id = get_sticky_provider(client_key)
    ordered = _order_candidates(candidates, sticky_id)
    if not ordered:
        return None, "local-stub"

    last_id = "local-stub"
    for provider in ordered:
        last_id = provider.id
        try:
            text = await generate_text(
                provider.id,
                prompt,
                max_tokens=max_tokens,
                task_intent=task_intent,
            )
            if text and text.strip():
                provider_id = _record_success(db, provider)
                set_sticky_provider(client_key, provider_id)
                return text.strip(), provider_id
            _mark_failure(db, provider, "empty response")
            logger.warning("Provider %s returned empty text — trying next", provider.id)
        except LlmHttpError as exc:
            _mark_failure(db, provider, str(exc), status_code=exc.status_code)
            logger.warning("Provider %s HTTP %s — trying next", provider.id, exc.status_code)
        except Exception as exc:
            _mark_failure(db, provider, str(exc))
            logger.warning("Provider %s failed (%s) — trying next", provider.id, exc)
    return None, last_id
