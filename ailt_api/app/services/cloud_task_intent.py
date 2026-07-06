"""Map cloud AI endpoints / OCR content types to a task intent for provider-specific models."""

from __future__ import annotations

from enum import Enum


class CloudTaskIntent(str, Enum):
    JOURNAL = "journal"
    TUTOR = "tutor"
    CODING = "coding"
    STRUCTURE = "structure"
    GENERAL = "general"


def intent_from_ocr_content_type(content_type: str) -> CloudTaskIntent:
    ct = (content_type or "prose").strip().lower()
    if ct in {"code", "programming", "sql", "script"}:
        return CloudTaskIntent.CODING
    if ct in {"math", "equation", "formula", "diagram", "flowchart", "table"}:
        return CloudTaskIntent.STRUCTURE
    return CloudTaskIntent.GENERAL
