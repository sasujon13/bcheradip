"""OTP email — loads deploy/email-preview-otp.html and fills {{placeholders}}."""

from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path

OTP_TEMPLATE_VERSION = "otp-email-preview"
_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "deploy" / "email-preview-otp.html"


@lru_cache(maxsize=1)
def _load_template() -> str:
    if not _TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Email template missing: {_TEMPLATE_PATH}")
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _code_digits_html(code: str) -> str:
    return "".join(
        f'<span style="display:inline-block;min-width:36px;text-align:center;">{html.escape(ch)}</span>'
        for ch in code.strip()
    )


def render_otp_html(*, purpose: str, code: str, ttl_minutes: int) -> str:
    return (
        _load_template()
        .replace("{{purpose}}", html.escape(purpose))
        .replace("{{code}}", html.escape(code.strip()))
        .replace("{{code_digits}}", _code_digits_html(code))
        .replace("{{ttl_minutes}}", str(int(ttl_minutes)))
    )


def render_otp_plain(*, purpose: str, code: str, ttl_minutes: int) -> str:
    return (
        f"AI Language Tutor — {purpose}\n\n"
        f"Your verification code is: {code.strip()}\n\n"
        f"This code expires in {ttl_minutes} minutes.\n"
        f"If you did not request this, ignore this message.\n\n"
        f"— Cheradip (AI Language Tutor)\n"
        f"https://cheradip.com\n"
    )
