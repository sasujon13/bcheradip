"""Google Play Billing gateway — server-side purchase verification.

The AI Language Tutor Android app buys subscriptions through Google Play. The
purchase token the client sends is untrusted: this module validates it against
the Play Developer API (androidpublisher ``purchases.subscriptionsv2``) so the
server grants entitlement only for real, paid, active subscriptions.

Auth uses a Google service-account key (JWT bearer → OAuth2 access token). We
sign the JWT with ``cryptography`` (already a dependency) and exchange it at
Google's token endpoint, so no extra Google client libraries are required.

When ``google_play_service_account_json`` is unset the gateway is *disabled*
and callers fall back to a DEV-only path that trusts the client — never leave
it unset in production.

Also parses Real-Time Developer Notifications (RTDN) delivered via Cloud
Pub/Sub push so renewals, cancellations, grace periods and refunds keep the
local subscription state in sync.

Docs: https://developer.android.com/google/play/billing/rtdn-reference
      https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.config import settings

logger = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_API_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3"
_TIMEOUT = 20.0

# Subscription states that still grant the user access (canceled keeps access
# until the paid period ends; grace period is a payment retry with access).
_ACTIVE_STATES = {
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
    "SUBSCRIPTION_STATE_CANCELED",
}

_sa_cache: dict | None = None
_sa_loaded = False
_token_cache: dict = {"access_token": None, "exp": 0.0}


@dataclass
class PlayVerification:
    """Normalized result of verifying a Play subscription purchase token."""

    active: bool
    state: str
    product_id: str | None
    expiry_ms: int | None
    acknowledged: bool
    auto_renewing: bool
    order_id: str | None
    linked_purchase_token: str | None


@dataclass
class RtdnNotification:
    """A decoded Play developer notification (subscription lifecycle)."""

    purchase_token: str
    notification_type: int
    subscription_id: str | None


def _load_service_account() -> dict | None:
    global _sa_cache, _sa_loaded
    if _sa_loaded:
        return _sa_cache
    _sa_loaded = True
    raw = (settings.google_play_service_account_json or "").strip()
    if not raw:
        _sa_cache = None
        return None
    try:
        if raw.startswith("{"):
            _sa_cache = json.loads(raw)
        else:
            with open(raw, encoding="utf-8") as fh:
                _sa_cache = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.error("Google Play service account load failed: %s", exc)
        _sa_cache = None
    return _sa_cache


def enabled() -> bool:
    return bool(settings.google_play_package_name and _load_service_account())


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _access_token() -> str | None:
    now = time.time()
    if _token_cache["access_token"] and _token_cache["exp"] - 60 > now:
        return _token_cache["access_token"]
    sa = _load_service_account()
    if not sa:
        return None
    try:
        iat = int(now)
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64url(
            json.dumps(
                {
                    "iss": sa["client_email"],
                    "scope": _SCOPE,
                    "aud": _TOKEN_URI,
                    "iat": iat,
                    "exp": iat + 3600,
                }
            ).encode()
        )
        signing_input = f"{header}.{claims}".encode()
        key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        assertion = f"{header}.{claims}.{_b64url(signature)}"
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _TOKEN_URI,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
        if resp.status_code >= 400:
            logger.error("Google token exchange failed: %s %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        token = data.get("access_token")
        if not token:
            return None
        _token_cache["access_token"] = token
        _token_cache["exp"] = now + float(data.get("expires_in", 3600))
        return token
    except Exception as exc:  # noqa: BLE001
        logger.error("Google token exchange error: %s", exc)
        return None


def _parse_rfc3339_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def verify_subscription(product_id: str, purchase_token: str) -> PlayVerification | None:
    """Verify a subscription purchase token with Google.

    Returns a :class:`PlayVerification` (active or not) on a definitive answer,
    or ``None`` if Google could not be reached / auth failed (caller should
    treat as a transient error, not "not entitled").
    """
    token = _access_token()
    if not token:
        return None
    pkg = settings.google_play_package_name
    url = f"{_API_BASE}/applications/{pkg}/purchases/subscriptionsv2/tokens/{purchase_token}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
    except Exception as exc:  # noqa: BLE001
        logger.error("Google Play verify request failed: %s", exc)
        return None

    if resp.status_code == 404 or resp.status_code == 410:
        # Token unknown or purged (long expired) → definitively not entitled.
        return PlayVerification(
            active=False,
            state="SUBSCRIPTION_STATE_EXPIRED",
            product_id=None,
            expiry_ms=None,
            acknowledged=False,
            auto_renewing=False,
            order_id=None,
            linked_purchase_token=None,
        )
    if resp.status_code >= 400:
        logger.error("Google Play verify %s: %s", resp.status_code, resp.text[:400])
        return None

    data = resp.json()
    state = data.get("subscriptionState", "")
    line_items = data.get("lineItems") or []

    verified_product: str | None = None
    expiry_ms: int | None = None
    auto_renewing = False
    for item in line_items:
        pid = item.get("productId")
        if pid:
            verified_product = pid
        item_expiry = _parse_rfc3339_ms(item.get("expiryTime"))
        if item_expiry and (expiry_ms is None or item_expiry > expiry_ms):
            expiry_ms = item_expiry
        if item.get("autoRenewingPlan", {}).get("autoRenewEnabled"):
            auto_renewing = True

    ack_state = data.get("acknowledgementState", "")
    now_ms = int(time.time() * 1000)
    not_expired = expiry_ms is None or expiry_ms > now_ms
    active = state in _ACTIVE_STATES and not_expired

    if verified_product and product_id and verified_product != product_id:
        logger.warning(
            "Play product mismatch: client=%s verified=%s (token=%s…)",
            product_id,
            verified_product,
            purchase_token[:12],
        )

    return PlayVerification(
        active=active,
        state=state or "SUBSCRIPTION_STATE_UNSPECIFIED",
        product_id=verified_product,
        expiry_ms=expiry_ms,
        acknowledged=ack_state == "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
        auto_renewing=auto_renewing,
        order_id=data.get("latestOrderId"),
        linked_purchase_token=data.get("linkedPurchaseToken"),
    )


def acknowledge_subscription(purchase_token: str) -> bool:
    """Acknowledge a subscription purchase server-side (idempotent on Play)."""
    token = _access_token()
    if not token:
        return False
    pkg = settings.google_play_package_name
    url = (
        f"{_API_BASE}/applications/{pkg}/purchases/subscriptionsv2/tokens/"
        f"{purchase_token}:acknowledge"
    )
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, headers={"Authorization": f"Bearer {token}"}, json={})
        if resp.status_code >= 400:
            logger.error("Play acknowledge %s: %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Play acknowledge error: %s", exc)
        return False


def parse_rtdn(payload: bytes) -> RtdnNotification | None:
    """Decode a Pub/Sub push envelope carrying a Play developer notification.

    Returns a subscription notification, or ``None`` for non-subscription
    messages (test pings, one-time products, voided purchases handled
    elsewhere) or malformed payloads.
    """
    try:
        envelope = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("RTDN envelope parse failed: %s", exc)
        return None

    message = envelope.get("message") or {}
    encoded = message.get("data")
    if not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        notification = json.loads(decoded)
    except (binascii.Error, ValueError) as exc:
        logger.error("RTDN data decode failed: %s", exc)
        return None

    sub = notification.get("subscriptionNotification")
    if not sub:
        # testNotification / oneTimeProductNotification / voidedPurchase — ignore.
        return None
    purchase_token = sub.get("purchaseToken")
    if not purchase_token:
        return None
    return RtdnNotification(
        purchase_token=purchase_token,
        notification_type=int(sub.get("notificationType", 0) or 0),
        subscription_id=sub.get("subscriptionId"),
    )
