"""Optional Google Translate fallback for cloud API JSON (cheradip-style X-Language)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)

# Never block admin/billing/promo/referral on Home AI translate — causes client timeouts.
_SKIP_TRANSLATE_PATH_PREFIXES = (
    "/api/ailt/admin/",
    "/api/ailt/promo/",
    "/api/ailt/referral/",
    "/api/ailt/billing/",
    "/api/ailt/device/",
    "/api/ailt/health",
    "/api/ailt/languages/",
    "/api/ailt/auth/",
)


def _walk_strings(obj: Any, acc: list[str], key: str | None = None) -> None:
    if isinstance(obj, str) and obj.strip():
        if key not in _SKIP_TRANSLATE_KEYS:
            acc.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk_strings(v, acc, k)
    elif isinstance(obj, list):
        for item in obj:
            _walk_strings(item, acc, key)


_SKIP_TRANSLATE_KEYS = frozenset(
    {
        "code",
        "productId",
        "product_id",
        "languageCode",
        "language_code",
        "id",
        "purchaseToken",
        "purchase_token",
        "display_name",
        "displayName",
        "health",
        "tier",
        "mode",
        "email",
        "whatsapp",
        "username",
        "sessionToken",
        "last_error",
        "lastError",
    }
)


def _apply_map(obj: Any, mapping: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return mapping.get(obj, obj)
    if isinstance(obj, dict):
        return {k: _apply_map(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_apply_map(i, mapping) for i in obj]
    return obj


def _should_translate(path: str) -> bool:
    if not settings.translate_api_responses:
        return False
    if any(path.startswith(prefix) for prefix in _SKIP_TRANSLATE_PATH_PREFIXES):
        return False
    return path.startswith("/api/ailt")


class TranslateResponseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        lang = request.headers.get("x-language", "").strip().lower()
        response = await call_next(request)
        if not lang or lang == "en" or not _should_translate(request.url.path):
            return response
        if response.status_code != 200:
            return response
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

        strings: list[str] = []
        _walk_strings(data, strings)
        unique = list(dict.fromkeys(strings))[:80]
        if not unique:
            return JSONResponse(data)

        mapping = {s: s for s in unique}
        try:
            timeout = httpx.Timeout(settings.translate_api_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    settings.home_ai_translate_url,
                    json={
                        "target_language": lang,
                        "source_language": "en",
                        "strings": {f"k{i}": t for i, t in enumerate(unique)},
                    },
                )
                if resp.status_code == 200:
                    translations = resp.json().get("translations", {})
                    for i, text in enumerate(unique):
                        mapping[text] = translations.get(f"k{i}", text)
        except Exception as e:
            logger.warning("API translate middleware failed (%s): %s", request.url.path, e)

        translated = _apply_map(data, mapping)
        return JSONResponse(translated)
