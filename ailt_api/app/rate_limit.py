"""Small process-local limiter for public authentication endpoints.

The reverse proxy should also rate-limit these routes. This layer protects
development installs and remains a useful second boundary in production.
"""

from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
from ipaddress import ip_address
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request

_events: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        trusted_proxy = ip_address(peer).is_loopback or ip_address(peer).is_private
    except ValueError:
        trusted_proxy = False
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded if trusted_proxy and forwarded else peer


def enforce_rate_limit(
    request: Request,
    scope: str,
    *,
    limit: int,
    window_seconds: int,
    identity: str = "",
) -> None:
    identity_digest = sha256(identity.strip().lower().encode("utf-8")).hexdigest()[:16]
    key = f"{scope}:{_client_ip(request)}:{identity_digest}"
    now = monotonic()
    cutoff = now - window_seconds
    with _lock:
        bucket = _events[key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            raise HTTPException(
                429,
                "Too many attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


def clear_rate_limits() -> None:
    """Test helper."""
    with _lock:
        _events.clear()
