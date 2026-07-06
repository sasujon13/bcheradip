"""Resolve provider-specific model ids from cloud task intent."""

from __future__ import annotations

from app.config import settings
from app.services.cloud_task_intent import CloudTaskIntent


def _intent_key(task_intent: CloudTaskIntent | str | None) -> str:
    if task_intent is None:
        return CloudTaskIntent.GENERAL.value
    if isinstance(task_intent, CloudTaskIntent):
        return task_intent.value
    return str(task_intent).strip().lower() or CloudTaskIntent.GENERAL.value


def _pick(intent_key: str, *, default: str, fast: str, coding: str, complex: str) -> str:
    if intent_key == CloudTaskIntent.JOURNAL.value:
        return fast
    if intent_key == CloudTaskIntent.CODING.value:
        return coding
    if intent_key in {CloudTaskIntent.TUTOR.value, CloudTaskIntent.STRUCTURE.value}:
        return complex
    return default


def resolve_provider_model(provider_id: str, task_intent: CloudTaskIntent | str | None) -> str:
    key = _intent_key(task_intent)
    if provider_id == "gemini":
        return _pick(
            key,
            default=settings.gemini_model,
            fast=settings.gemini_model_fast,
            coding=settings.gemini_model_coding,
            complex=settings.gemini_model_complex,
        )
    if provider_id == "openai":
        return _pick(
            key,
            default=settings.openai_model_default,
            fast=settings.openai_model_fast,
            coding=settings.openai_model_coding,
            complex=settings.openai_model_complex,
        )
    if provider_id == "openai_paid":
        return _pick(
            key,
            default=settings.openai_paid_model_default,
            fast=settings.openai_paid_model_fast,
            coding=settings.openai_paid_model_coding,
            complex=settings.openai_paid_model_complex,
        )
    if provider_id == "groq":
        return _pick(
            key,
            default=settings.groq_model_default,
            fast=settings.groq_model_fast,
            coding=settings.groq_model_coding,
            complex=settings.groq_model_complex,
        )
    if provider_id == "claude":
        return _pick(
            key,
            default=settings.anthropic_model,
            fast=settings.anthropic_model_fast,
            coding=settings.anthropic_model_coding,
            complex=settings.anthropic_model_complex,
        )
    if provider_id == "claude_paid":
        return _pick(
            key,
            default=settings.anthropic_paid_model,
            fast=settings.anthropic_paid_model_fast,
            coding=settings.anthropic_paid_model_coding,
            complex=settings.anthropic_paid_model_complex,
        )
    if provider_id == "mistral":
        return _pick(
            key,
            default=settings.mistral_model_default,
            fast=settings.mistral_model_fast,
            coding=settings.mistral_model_coding,
            complex=settings.mistral_model_complex,
        )
    if provider_id == "openrouter":
        return _pick(
            key,
            default=settings.openrouter_model,
            fast=settings.openrouter_model_fast,
            coding=settings.openrouter_model_coding,
            complex=settings.openrouter_model_complex,
        )
    if provider_id == "openrouter_paid":
        return _pick(
            key,
            default=settings.openrouter_paid_model,
            fast=settings.openrouter_paid_model_fast,
            coding=settings.openrouter_paid_model_coding,
            complex=settings.openrouter_paid_model_complex,
        )
    raise ValueError(f"Unknown provider id: {provider_id}")
