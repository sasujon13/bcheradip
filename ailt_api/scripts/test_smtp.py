#!/usr/bin/env python3
"""Test Brevo SMTP + OTP email template."""

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
    from app.services.email_service import build_multipart_message, message_has_html_part, send_otp_email
    from app.services.email_templates import OTP_TEMPLATE_VERSION, _TEMPLATE_PATH, render_otp_html, render_otp_plain

    print("=== SMTP config ===")
    print(f"SMTP_ENABLED={settings.smtp_enabled}")
    print(f"SMTP_HOST={settings.smtp_host}")
    print(f"SMTP_FROM={settings.smtp_from}")
    print(f"Template: {OTP_TEMPLATE_VERSION}")
    print(f"HTML file: {_TEMPLATE_PATH} ({'OK' if _TEMPLATE_PATH.is_file() else 'MISSING'})")

    if not _TEMPLATE_PATH.is_file():
        print(f"FAILED: template not found at {_TEMPLATE_PATH}", file=sys.stderr)
        return 1

    if not settings.smtp_enabled:
        print("FAILED: SMTP_ENABLED is false", file=sys.stderr)
        return 1

    if not settings.smtp_user or not settings.smtp_password:
        print("FAILED: SMTP_USER and SMTP_PASSWORD must be set in .env", file=sys.stderr)
        return 1

    html = render_otp_html(purpose="SMTP test", code="123456", ttl_minutes=settings.otp_ttl_minutes)
    plain = render_otp_plain(purpose="SMTP test", code="123456", ttl_minutes=settings.otp_ttl_minutes)
    print(f"HTML size: {len(html)} bytes")

    preview = args.save_preview or ROOT / "deploy" / "email-preview-otp.html.out"
    preview.write_text(html, encoding="utf-8")
    print(f"Preview: {preview}")

    probe = build_multipart_message(to=args.to, subject="probe", plain_body=plain, html_body=html)
    if not message_has_html_part(probe):
        print("FAILED: MIME message has no text/html part", file=sys.stderr)
        return 1
    print("MIME check: multipart/alternative + text/html — OK")

    try:
        send_otp_email(to=args.to, purpose="SMTP test", code="123456")
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print(f"OK — email sent to {args.to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
