"""Unit tests for provider model selection by cloud task intent."""

from __future__ import annotations

from app.services.cloud_task_intent import CloudTaskIntent, intent_from_ocr_content_type
from app.services.mistral_models import resolve_mistral_model
from app.services.provider_models import resolve_provider_model


def test_gemini_journal_uses_flash_lite():
    assert resolve_provider_model("gemini", CloudTaskIntent.JOURNAL) == "gemini-flash-lite-latest"


def test_gemini_coding_uses_flash():
    assert resolve_provider_model("gemini", CloudTaskIntent.CODING) == "gemini-2.5-flash"


def test_openai_paid_coding_uses_o4_mini():
    assert resolve_provider_model("openai_paid", CloudTaskIntent.CODING) == "o4-mini"


def test_groq_tutor_uses_70b():
    assert resolve_provider_model("groq", CloudTaskIntent.TUTOR) == "llama-3.3-70b-versatile"


def test_groq_coding_uses_qwen():
    assert resolve_provider_model("groq", CloudTaskIntent.CODING) == "qwen/qwen3-32b"


def test_claude_paid_tutor_uses_sonnet():
    assert resolve_provider_model("claude_paid", CloudTaskIntent.TUTOR) == "claude-sonnet-4-5"


def test_openrouter_coding_uses_coder_free():
    assert resolve_provider_model("openrouter", CloudTaskIntent.CODING) == "qwen/qwen3-coder:free"


def test_mistral_journal_uses_fast_alias():
    assert resolve_mistral_model(CloudTaskIntent.JOURNAL) == "ministral-3b-latest"


def test_intent_from_ocr_code():
    assert intent_from_ocr_content_type("code") == CloudTaskIntent.CODING


def test_intent_from_ocr_math():
    assert intent_from_ocr_content_type("math") == CloudTaskIntent.STRUCTURE
