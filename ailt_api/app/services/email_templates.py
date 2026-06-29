"""OTP email — loads deploy/email-preview-otp.html and fills {{placeholders}}."""

from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path

from app.config import settings

OTP_TEMPLATE_VERSION = "otp-email-preview"
LOGO_CID = "cheradip-logo"

_DEPLOY_DIR = Path(__file__).resolve().parent.parent.parent / "deploy"
_TEMPLATE_PATH = _DEPLOY_DIR / "email-preview-otp.html"
_LOGO_PATH = _DEPLOY_DIR / "cheradip.png"


@lru_cache(maxsize=1)
def _load_template() -> str:
    if not _TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Email template missing: {_TEMPLATE_PATH}")
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def logo_path() -> Path:
    return _LOGO_PATH


def logo_public_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/email/cheradip.png"


def logo_img_src() -> str:
    """Short cid: or https URL — Brevo strips long data: URIs (removes src entirely)."""
    if _LOGO_PATH.is_file():
        return f"cid:{LOGO_CID}"
    return logo_public_url()


def _code_digits_html(code: str) -> str:
    return "".join(
        f'<span style="display:inline-block;min-width:36px;text-align:center;">{html.escape(ch)}</span>'
        for ch in code.strip()
    )


def render_otp_html(*, purpose: str, code: str, ttl_minutes: int) -> str:
    logo_src = logo_img_src()
    return (
        _load_template()
        .replace("{{purpose}}", html.escape(purpose))
        .replace("{{code}}", html.escape(code.strip()))
        .replace("{{code_digits}}", _code_digits_html(code))
        .replace("{{ttl_minutes}}", str(int(ttl_minutes)))
        .replace("{{logo_src}}", logo_src)
        .replace('src="cheradip.png"', f'src="{logo_src}"')
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
