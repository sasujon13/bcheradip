"""Backward-compatible Mistral resolver — prefer provider_models.resolve_provider_model."""

from __future__ import annotations

from app.services.cloud_task_intent import CloudTaskIntent
from app.services.provider_models import resolve_provider_model


def resolve_mistral_model(task_intent: CloudTaskIntent | str | None) -> str:
    return resolve_provider_model("mistral", task_intent)
