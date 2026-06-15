"""Outbound email via SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _smtp_send(msg: EmailMessage) -> None:
    timeout = 30
    if settings.smtp_use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout, context=context) as smtp:
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
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
