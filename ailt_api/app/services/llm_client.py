"""Cloud LLM calls — Gemini, OpenAI, Groq. Falls back to template when no keys."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services.provider_models import resolve_provider_model

logger = logging.getLogger(__name__)


class LlmHttpError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


def _provider_key(provider_id: str, database_key: str | None = None) -> str:
    if database_key and database_key.strip():
        return database_key.strip()
    if provider_id == "gemini":
        return settings.gemini_api_key
    if provider_id in ("openai", "openai_paid"):
        return settings.openai_api_key
    if provider_id == "groq":
        return settings.groq_api_key
    if provider_id in ("claude", "claude_paid"):
        return settings.anthropic_api_key
    if provider_id == "mistral":
        return settings.mistral_api_key
    if provider_id in ("openrouter", "openrouter_paid"):
        return settings.openrouter_api_key
    return ""


def provider_has_key(provider_id: str, database_key: str | None = None) -> bool:
    return bool(_provider_key(provider_id, database_key))


def _format_http_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            msg = err.get("message") or err.get("type") or str(err)
        else:
            msg = str(err)
    except Exception:
        msg = (resp.text or resp.reason_phrase or "request failed")[:240]
    return f"HTTP {resp.status_code}: {msg}"


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    body: dict,
) -> dict:
    resp = await client.post(url, headers=headers, json=body)
    if resp.is_error:
        raise LlmHttpError(resp.status_code, _format_http_error(resp))
    return resp.json()


async def generate_text(
    provider_id: str,
    prompt: str,
    max_tokens: int = 512,
    *,
    task_intent: str | None = None,
    api_key: str | None = None,
) -> str | None:
    model = resolve_provider_model(provider_id, task_intent)
    key = _provider_key(provider_id, api_key)
    if provider_id == "gemini" and key:
        return await _gemini(prompt, max_tokens, model=model, api_key=key)
    if provider_id in ("openai", "openai_paid") and key:
        return await _openai(prompt, max_tokens, model=model, api_key=key)
    if provider_id == "groq" and key:
        return await _groq(prompt, max_tokens, model=model, api_key=key)
    if provider_id in ("claude", "claude_paid") and key:
        return await _anthropic(prompt, max_tokens, model=model, api_key=key)
    if provider_id == "mistral" and key:
        return await _mistral(prompt, max_tokens, model=model, api_key=key)
    if provider_id in ("openrouter", "openrouter_paid") and key:
        return await _openrouter(prompt, max_tokens, model=model, api_key=key)
    return None


async def _gemini(prompt: str, max_tokens: int, *, model: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(
            client,
            url,
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": api_key,
            },
            body=body,
        )
        parts = data["candidates"][0]["content"]["parts"]
        return parts[0].get("text", "").strip()


async def _openai(prompt: str, max_tokens: int, model: str = "gpt-4o-mini", api_key: str = "") -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(
            client,
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
        )
        return data["choices"][0]["message"]["content"].strip()


async def _groq(prompt: str, max_tokens: int, *, model: str, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(
            client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
        )
        return data["choices"][0]["message"]["content"].strip()


async def _anthropic(prompt: str, max_tokens: int, model: str, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(
            client,
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return data["content"][0]["text"].strip()


async def _mistral(prompt: str, max_tokens: int, model: str, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(
            client,
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
        )
        return data["choices"][0]["message"]["content"].strip()


async def _openrouter(prompt: str, max_tokens: int, model: str, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _post_json(
            client,
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.public_base_url,
                "X-Title": "AI Language Tutor",
            },
            body={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
        )
        return data["choices"][0]["message"]["content"].strip()
