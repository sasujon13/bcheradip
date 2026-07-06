"""Unit tests for LLM provider routing (failures, sticky order)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import ai_session_affinity
from app.services.llm_router import (
    FAILURE_EXHAUST_THRESHOLD,
    _mark_failure,
    _order_candidates,
    _record_success,
    ensure_daily_quota_reset,
)


def test_mark_failure_429_counts_toward_exhausted():
    db = MagicMock()
    provider = SimpleNamespace(
        last_error=None,
        consecutive_failures=FAILURE_EXHAUST_THRESHOLD - 1,
        health="healthy",
    )
    _mark_failure(db, provider, "HTTP 429: limit", status_code=429)
    assert provider.health == "exhausted"
    assert provider.consecutive_failures == FAILURE_EXHAUST_THRESHOLD


def test_mark_failure_429_below_threshold_stays_degraded():
    db = MagicMock()
    provider = SimpleNamespace(
        last_error=None,
        consecutive_failures=2,
        health="healthy",
    )
    _mark_failure(db, provider, "HTTP 429: limit", status_code=429)
    assert provider.health == "degraded"
    assert provider.consecutive_failures == 3
    db.commit.assert_called_once()


def test_mark_failure_seventh_error_marks_exhausted():
    db = MagicMock()
    provider = SimpleNamespace(
        last_error=None,
        consecutive_failures=FAILURE_EXHAUST_THRESHOLD - 1,
        health="healthy",
    )
    _mark_failure(db, provider, "HTTP 500: boom")
    assert provider.health == "exhausted"
    assert provider.consecutive_failures == FAILURE_EXHAUST_THRESHOLD


def test_record_success_does_not_exhaust_on_high_request_count():
    db = MagicMock()
    provider = SimpleNamespace(
        id="mistral",
        requests_today=9999,
        consecutive_failures=0,
        last_used_at_ms=0,
        last_error="old",
        health="healthy",
        quota_daily_limit=None,
    )
    provider_id = _record_success(db, provider)
    assert provider_id == "mistral"
    assert provider.requests_today == 10000
    assert provider.health == "healthy"


def test_daily_quota_reset_once_per_utc_day():
    db = MagicMock()
    routing = SimpleNamespace(quota_reset_day_utc=None)
    provider = SimpleNamespace(
        requests_today=99,
        consecutive_failures=3,
        health="exhausted",
        enabled=True,
        last_error="old",
    )
    db.scalar.return_value = routing
    db.scalars.return_value.all.return_value = [provider]

    ensure_daily_quota_reset(db)

    assert routing.quota_reset_day_utc is not None
    assert provider.requests_today == 0
    assert provider.consecutive_failures == 0
    assert provider.health == "healthy"
    assert provider.last_error is None


def test_order_candidates_puts_sticky_first():
    groq = SimpleNamespace(id="groq")
    gemini = SimpleNamespace(id="gemini")
    openai = SimpleNamespace(id="openai")
    pool = [groq, gemini, openai]
    with patch("app.services.llm_router.random.shuffle", side_effect=lambda xs: xs.reverse()):
        ordered = _order_candidates(pool, "gemini")
    assert ordered[0].id == "gemini"
    assert {p.id for p in ordered} == {"groq", "gemini", "openai"}


def test_sticky_provider_ttl():
    ai_session_affinity._sticky.clear()
    ai_session_affinity.set_sticky_provider("device:test", "groq")
    assert ai_session_affinity.get_sticky_provider("device:test") == "groq"
    ai_session_affinity._sticky["device:test"] = ("groq", 1)  # expired
    assert ai_session_affinity.get_sticky_provider("device:test") is None
