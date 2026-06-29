"""Outbound email via SMTP (Brevo in production)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings
from app.services.email_templates import render_otp_html, render_otp_plain

logger = logging.getLogger(__name__)

_LOCAL_POSTFIX_ERROR = (
    "SMTP is set to 127.0.0.1:25 (local mail). Use Brevo: "
    "SMTP_HOST=smtp-relay.brevo.com — see deploy/BREVO_EMAIL.md"
)


def _ensure_smtp_can_reach_inbox() -> None:
    if settings.smtp_enabled and settings.uses_local_postfix_direct():
        raise RuntimeError(_LOCAL_POSTFIX_ERROR)


def _ssl_context_for_smtp() -> ssl.SSLContext:
    """Local dev SMTP on loopback may use a mismatched cert — skip verify there only."""
    host = settings.smtp_host.strip().lower()
    if host in {"127.0.0.1", "localhost", "::1"}:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def _smtp_send(msg: EmailMessage) -> None:
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
    target = to.strip()
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = target
    msg["Subject"] = subject
    msg.set_content(plain_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if settings.smtp_enabled:
        _ensure_smtp_can_reach_inbox()
        try:
            _smtp_send(msg)
            logger.info("Sent email to %s: %s", target, subject)
        except Exception as exc:
            logger.exception("SMTP send failed for %s", target)
            if not settings.dev_log_otp:
                raise RuntimeError("Could not send email") from exc

    if settings.dev_log_otp:
        print(f"[EMAIL] From: {settings.smtp_from} To: {target}\nSubject: {subject}\n{plain_body}\n---")


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
