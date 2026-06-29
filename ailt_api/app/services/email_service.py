"""Outbound email via SMTP (Brevo in production)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from app.config import settings
from app.services.email_templates import (
    OTP_TEMPLATE_VERSION,
    email_image_urls,
    render_otp_html,
    render_otp_plain,
)

logger = logging.getLogger(__name__)

_LOCAL_POSTFIX_ERROR = (
    "SMTP is set to 127.0.0.1:25 (local mail). Use Brevo: "
    "SMTP_HOST=smtp-relay.brevo.com — see deploy/BREVO_EMAIL.md"
)


def _ensure_smtp_can_reach_inbox() -> None:
    if settings.smtp_enabled and settings.uses_local_postfix_direct():
        raise RuntimeError(_LOCAL_POSTFIX_ERROR)


def _from_header() -> str:
    name, addr = parseaddr(settings.smtp_from)
    if addr:
        return formataddr((name, addr))
    return settings.smtp_from.strip()


def _ssl_context_for_smtp() -> ssl.SSLContext:
    host = settings.smtp_host.strip().lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def build_multipart_message(
    *,
    to: str,
    subject: str,
    plain_body: str,
    html_body: str,
) -> MIMEMultipart:
    """multipart/alternative with HTTPS-hosted logo URLs in HTML (Brevo strips cid: inline)."""
    if not html_body or "<html" not in html_body.lower():
        raise ValueError("HTML body missing or invalid — branded template required")

    msg = MIMEMultipart("alternative")
    msg["From"] = _from_header()
    msg["To"] = to.strip()
    msg["Subject"] = subject
    msg["X-AILT-Template"] = OTP_TEMPLATE_VERSION
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _smtp_send(msg: MIMEMultipart) -> None:
    timeout = 30
    context = _ssl_context_for_smtp()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout, context=context) as smtp:
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=context)
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def send_email(*, to: str, subject: str, plain_body: str, html_body: str | None = None) -> None:
    if not settings.smtp_enabled:
        raise RuntimeError("SMTP_ENABLED is false — set SMTP_ENABLED=true in .env")

    target = to.strip()
    if not html_body:
        raise RuntimeError("HTML body required — use send_otp_email for OTP mail")

    msg = build_multipart_message(
        to=target,
        subject=subject,
        plain_body=plain_body,
        html_body=html_body,
    )

    _ensure_smtp_can_reach_inbox()
    try:
        _smtp_send(msg)
        logger.info(
            "Sent HTML email to %s: %s (%s, %d byte html, logo urls=%s)",
            target,
            subject,
            OTP_TEMPLATE_VERSION,
            len(html_body),
            email_image_urls(),
        )
    except smtplib.SMTPAuthenticationError as exc:
        logger.exception("SMTP auth failed for %s", target)
        raise RuntimeError(
            "SMTP authentication failed — check Brevo SMTP key and SMTP_USER login"
        ) from exc
    except smtplib.SMTPException as exc:
        logger.exception("SMTP send failed for %s", target)
        raise RuntimeError(f"SMTP error: {exc}") from exc
    except OSError as exc:
        logger.exception("SMTP connection failed for %s", target)
        raise RuntimeError(f"Could not connect to SMTP server: {exc}") from exc
    except Exception as exc:
        logger.exception("SMTP send failed for %s", target)
        raise RuntimeError(f"Could not send email: {exc}") from exc

    if settings.dev_log_otp:
        print(f"[EMAIL] From: {msg['From']} To: {target}\nSubject: {subject}\n{plain_body}\n---")


def send_otp_email(*, to: str, purpose: str, code: str) -> None:
    ttl = settings.otp_ttl_minutes
    plain = render_otp_plain(purpose=purpose, code=code, ttl_minutes=ttl)
    html = render_otp_html(purpose=purpose, code=code, ttl_minutes=ttl)
    send_email(
        to=to,
        subject=f"AI Language Tutor — {purpose} code",
        plain_body=plain,
        html_body=html,
    )


def message_has_html_part(msg: MIMEMultipart) -> bool:
    return any(part.get_content_type() == "text/html" for part in msg.walk())


def message_logo_url_count(msg: MIMEMultipart) -> int:
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                return html.count("cheradip-avatar.png") + html.count("cheradip-wordmark.png")
    return 0
