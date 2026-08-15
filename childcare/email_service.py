"""Outbound OTP email via the same Brevo SMTP credentials as AI Language Tutor."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

LOGO_CID = "cheradip-logo"
AILT_DEPLOY = Path(settings.BASE_DIR) / "ailt_api" / "deploy"
LOGO_PATH = AILT_DEPLOY / "cheradip.png"


def _smtp_host() -> str:
    host = (getattr(settings, "SMTP_HOST", "") or "").strip()
    if host:
        return host
    return (getattr(settings, "EMAIL_HOST", "") or "").strip()


def _smtp_port() -> int:
    if getattr(settings, "SMTP_HOST", ""):
        return int(getattr(settings, "SMTP_PORT", 587) or 587)
    return int(getattr(settings, "EMAIL_PORT", 587) or 587)


def _smtp_user() -> str:
    if getattr(settings, "SMTP_HOST", ""):
        return (getattr(settings, "SMTP_USER", "") or "").strip()
    return (getattr(settings, "EMAIL_HOST_USER", "") or "").strip()


def _smtp_password() -> str:
    if getattr(settings, "SMTP_HOST", ""):
        return (getattr(settings, "SMTP_PASSWORD", "") or "").strip()
    return (getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip()


def _smtp_from() -> str:
    value = (getattr(settings, "SMTP_FROM", "") or "").strip()
    if value:
        return value
    return (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "Cheradip <noreply@cheradip.com>").strip()


def _from_header() -> str:
    name, addr = parseaddr(_smtp_from())
    if addr:
        return formataddr((name, addr))
    return _smtp_from()


def _ssl_context() -> ssl.SSLContext:
    host = _smtp_host().lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def _attach_logo(related: MIMEMultipart) -> None:
    if not LOGO_PATH.is_file():
        return
    img = MIMEImage(LOGO_PATH.read_bytes(), _subtype="png")
    img.add_header("Content-ID", f"<{LOGO_CID}>")
    img.add_header("Content-Disposition", "inline", filename="cheradip.png")
    related.attach(img)


def _render_plain(*, purpose: str, code: str, ttl_minutes: int) -> str:
    return (
        f"Child Care — {purpose}\n\n"
        f"Your verification code is: {code}\n"
        f"It expires in {ttl_minutes} minutes.\n\n"
        f"If you did not request this, ignore this email.\n"
    )


def _render_html(*, purpose: str, code: str, ttl_minutes: int) -> str:
    logo_src = f"cid:{LOGO_CID}" if LOGO_PATH.is_file() else ""
    logo_html = (
        f'<img src="{logo_src}" alt="Cheradip" width="120" style="margin-bottom:16px;" />'
        if logo_src
        else ""
    )
    digits = "".join(
        f'<span style="display:inline-block;min-width:28px;text-align:center;'
        f'font-size:28px;font-weight:700;letter-spacing:2px;">{ch}</span>'
        for ch in code.strip()
    )
    return f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;background:#f6f8fa;padding:24px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;">
    {logo_html}
    <h2 style="color:#0d7377;margin:0 0 8px;">Child Care</h2>
    <p style="color:#333;">{purpose} code</p>
    <p style="margin:24px 0;">{digits}</p>
    <p style="color:#666;font-size:14px;">Expires in {ttl_minutes} minutes.</p>
  </div>
</body></html>"""


def send_otp_email(*, to: str, purpose: str, code: str) -> None:
    if not getattr(settings, "SMTP_ENABLED", True):
        raise RuntimeError("SMTP_ENABLED is false")

    host = _smtp_host()
    if not host:
        raise RuntimeError("SMTP_HOST / EMAIL_HOST not configured")

    ttl = int(getattr(settings, "OTP_TTL_MINUTES", 15) or 15)
    plain = _render_plain(purpose=purpose, code=code, ttl_minutes=ttl)
    html = _render_html(purpose=purpose, code=code, ttl_minutes=ttl)

    related = MIMEMultipart("related")
    related["From"] = _from_header()
    related["To"] = to.strip()
    related["Subject"] = f"Child Care — {purpose} code"

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(plain, "plain", "utf-8"))
    alternative.attach(MIMEText(html, "html", "utf-8"))
    related.attach(alternative)
    _attach_logo(related)

    user = _smtp_user()
    password = _smtp_password()
    port = _smtp_port()
    use_ssl = bool(getattr(settings, "SMTP_USE_SSL", False))
    use_tls = bool(getattr(settings, "SMTP_USE_TLS", True))
    if not getattr(settings, "SMTP_HOST", ""):
        use_tls = bool(getattr(settings, "EMAIL_USE_TLS", True))

    try:
        context = _ssl_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(related)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                if use_tls:
                    smtp.starttls(context=context)
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(related)
        logger.info("Child Care OTP email sent to %s (%s)", to, purpose)
    except smtplib.SMTPAuthenticationError as exc:
        logger.exception("SMTP auth failed for Child Care OTP")
        raise RuntimeError(
            "SMTP authentication failed — check Brevo SMTP_USER / SMTP_PASSWORD (same as AILT)"
        ) from exc
    except Exception as exc:
        logger.exception("Child Care OTP email failed")
        raise RuntimeError(f"Could not send email: {exc}") from exc
