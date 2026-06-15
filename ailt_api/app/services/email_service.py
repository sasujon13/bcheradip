"""Outbound email via SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

_LOCAL_POSTFIX_ERROR = (
    "SMTP is set to 127.0.0.1:25 (local Postfix, no auth). Gmail/Yahoo reject direct VPS delivery (550 5.7.1). "
    "Use port 587 with user admin and From noreply@cheradip.com — see deploy/MAIL_NOREPLY_CHERADIP.md"
)


def _ensure_smtp_can_reach_inbox() -> None:
    if settings.smtp_enabled and settings.uses_local_postfix_direct():
        raise RuntimeError(_LOCAL_POSTFIX_ERROR)


def _ssl_context_for_smtp() -> ssl.SSLContext:
    """Local Postfix on 127.0.0.1 uses a cert for mail.cheradip.com — skip verify on loopback."""
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


def send_email(*, to: str, subject: str, body: str) -> None:
    target = to.strip()
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = target
    msg["Subject"] = subject
    msg.set_content(body)

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
        print(f"[EMAIL] From: {settings.smtp_from} To: {target}\nSubject: {subject}\n{body}\n---")


def send_otp_email(*, to: str, purpose: str, code: str) -> None:
    send_email(
        to=to,
        subject=f"AI Language Tutor — {purpose} code",
        body=(
            f"Your verification code is: {code}\n\n"
            f"This code expires in {settings.otp_ttl_minutes} minutes.\n"
            f"If you did not request this, ignore this message.\n\n"
            f"— AI Language Tutor ({settings.smtp_from})"
        ),
    )
