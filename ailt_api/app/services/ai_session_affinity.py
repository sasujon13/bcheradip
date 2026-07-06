"""In-memory sticky provider per client (user or device) for faster follow-up AI calls."""

from __future__ import annotations

from app.security import ms_now

# Same client keeps the last successful provider for rapid follow-up requests.
STICKY_TTL_MS = 30 * 60 * 1000

_sticky: dict[str, tuple[str, int]] = {}


def get_sticky_provider(client_key: str | None) -> str | None:
    if not client_key:
        return None
    entry = _sticky.get(client_key)
    if not entry:
        return None
    provider_id, last_ms = entry
    if ms_now() - last_ms > STICKY_TTL_MS:
        _sticky.pop(client_key, None)
        return None
    return provider_id


def set_sticky_provider(client_key: str | None, provider_id: str) -> None:
    if not client_key or not provider_id or provider_id == "local-stub":
        return
    _sticky[client_key] = (provider_id, ms_now())


def clear_sticky_provider(client_key: str | None) -> None:
    if client_key:
        _sticky.pop(client_key, None)
