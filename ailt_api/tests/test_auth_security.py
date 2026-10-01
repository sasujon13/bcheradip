from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config import settings
from app.rate_limit import clear_rate_limits, enforce_rate_limit
from app.routers.billing import verify_purchase
from app.schemas import BillingVerifyRequest
from app.services import play_gateway


class _Request:
    client = SimpleNamespace(host="203.0.113.10")
    headers = {}


def test_public_rate_limit_rejects_repeated_attempts():
    clear_rate_limits()
    request = _Request()
    enforce_rate_limit(request, "test", limit=2, window_seconds=60, identity="person@example.com")
    enforce_rate_limit(request, "test", limit=2, window_seconds=60, identity="person@example.com")
    with pytest.raises(HTTPException) as caught:
        enforce_rate_limit(request, "test", limit=2, window_seconds=60, identity="person@example.com")
    assert caught.value.status_code == 429


def test_play_billing_fails_closed_without_verifier(monkeypatch):
    monkeypatch.setattr(play_gateway, "enabled", lambda: False)
    monkeypatch.setattr(settings, "allow_unverified_play_purchases", False)
    with pytest.raises(HTTPException) as caught:
        verify_purchase(
            BillingVerifyRequest(purchaseToken="unverified", productId="pro_monthly"),
            db=SimpleNamespace(),
            buyer=None,
        )
    assert caught.value.status_code == 503
