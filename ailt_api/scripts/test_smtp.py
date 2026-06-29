#!/usr/bin/env python3
"""Test Brevo SMTP + branded OTP template. Called by scripts/test_smtp.sh."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a test OTP email via Brevo")
    parser.add_argument("to", help="Recipient email address")
    parser.add_argument(
        "--save-preview",
        type=Path,
        default=None,
        help="Write rendered HTML to this path (debug)",
    )
    args = parser.parse_args()

    from app.config import settings
    from app.services.email_service import (
        build_multipart_message,
        message_has_html_part,
        message_inline_image_count,
        send_otp_email,
    )
    from app.services.email_templates import LOGO_AVATAR_PATH, LOGO_WORDMARK_PATH, OTP_TEMPLATE_VERSION, render_otp_html, render_otp_plain

    print("=== SMTP config ===")
    print(f"SMTP_ENABLED={settings.smtp_enabled}")
    print(f"SMTP_HOST={settings.smtp_host}")
    print(f"SMTP_PORT={settings.smtp_port}")
    print(f"SMTP_USER={settings.smtp_user or '(empty)'}")
    print(f"SMTP_FROM={settings.smtp_from}")
    print(f"SMTP_USE_TLS={settings.smtp_use_tls}")
    print(f"SMTP_USE_SSL={settings.smtp_use_ssl}")
    print(f"DEV_LOG_OTP={settings.dev_log_otp}")

    if not settings.smtp_enabled:
        print("FAILED: SMTP_ENABLED is false", file=sys.stderr)
        return 1

    host = settings.smtp_host.strip().lower()
    if host in {"127.0.0.1", "localhost"} and settings.smtp_port in {25, 1025}:
        print(
            f"FAILED: SMTP is {settings.smtp_host}:{settings.smtp_port} — "
            "local/dev mail will not reach Gmail. Use Brevo in .env",
            file=sys.stderr,
        )
        return 1

    if not settings.smtp_user or not settings.smtp_password:
        print("FAILED: SMTP_USER and SMTP_PASSWORD must be set in .env", file=sys.stderr)
        return 1

    if host != "smtp-relay.brevo.com":
        print(f"WARN: SMTP_HOST is '{settings.smtp_host}' — expected smtp-relay.brevo.com")

    logo = LOGO_AVATAR_PATH
    wordmark = LOGO_WORDMARK_PATH
    if not logo.is_file():
        print(f"WARN: avatar PNG missing at {logo} — run scripts/build-email-assets.sh")
    if not wordmark.is_file():
        print(f"WARN: wordmark PNG missing at {wordmark} — run scripts/build-email-assets.sh")

    html = render_otp_html(purpose="SMTP test", code="123456", ttl_minutes=settings.otp_ttl_minutes)
    plain = render_otp_plain(purpose="SMTP test", code="123456", ttl_minutes=settings.otp_ttl_minutes)
    print(f"Template version: {OTP_TEMPLATE_VERSION}")
    print(f"HTML template: {len(html)} bytes")
    if args.save_preview:
        args.save_preview.write_text(html, encoding="utf-8")
        print(f"Preview saved: {args.save_preview}")

    probe = build_multipart_message(
        to=args.to,
        subject="probe",
        plain_body=plain,
        html_body=html,
    )
    if not message_has_html_part(probe):
        print("FAILED: MIME message has no text/html part", file=sys.stderr)
        return 1
    imgs = message_inline_image_count(probe)
    print(f"MIME check: multipart/related + text/html + {imgs} inline PNG(s) — OK")
    if imgs == 0:
        print("WARN: no inline PNG logos — run scripts/build-email-assets.sh", file=sys.stderr)

    try:
        send_otp_email(to=args.to, purpose="SMTP test", code="123456")
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"OK — email sent to {args.to}. Check inbox and spam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
