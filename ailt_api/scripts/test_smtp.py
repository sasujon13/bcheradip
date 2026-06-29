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
        message_logo_url_count,
        send_otp_email,
    )
    from app.services.email_templates import (
        LOGO_AVATAR_PATH,
        LOGO_WORDMARK_PATH,
        OTP_TEMPLATE_VERSION,
        email_asset_url,
        email_image_urls,
        render_otp_html,
        render_otp_plain,
    )

    print("=== SMTP config ===")
    print(f"SMTP_ENABLED={settings.smtp_enabled}")
    print(f"SMTP_HOST={settings.smtp_host}")
    print(f"SMTP_PORT={settings.smtp_port}")
    print(f"SMTP_USER={settings.smtp_user or '(empty)'}")
    print(f"SMTP_FROM={settings.smtp_from}")
    print(f"SMTP_USE_TLS={settings.smtp_use_tls}")
    print(f"SMTP_USE_SSL={settings.smtp_use_ssl}")
    print(f"DEV_LOG_OTP={settings.dev_log_otp}")
    print(f"EMAIL_ASSETS_BASE={settings.resolved_email_assets_base_url()}")

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

    if not LOGO_AVATAR_PATH.is_file():
        print(f"WARN: avatar PNG missing at {LOGO_AVATAR_PATH} — run scripts/build-email-assets.sh")
    if not LOGO_WORDMARK_PATH.is_file():
        print(f"WARN: wordmark PNG missing at {LOGO_WORDMARK_PATH} — run scripts/build-email-assets.sh")

    html = render_otp_html(purpose="SMTP test", code="123456", ttl_minutes=settings.otp_ttl_minutes)
    plain = render_otp_plain(purpose="SMTP test", code="123456", ttl_minutes=settings.otp_ttl_minutes)
    print(f"Template version: {OTP_TEMPLATE_VERSION}")
    print(f"HTML template: {len(html)} bytes")
    print(f"Logo URLs: {email_image_urls()}")
    if "cid:" in html:
        print("FAILED: HTML still uses cid: — Brevo will not show inline images", file=sys.stderr)
        return 1
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
    refs = message_logo_url_count(probe)
    print(f"MIME check: multipart/alternative + text/html + {refs} logo URL ref(s) — OK")
    if refs == 0:
        print("WARN: HTML has no logo URLs — run scripts/build-email-assets.sh", file=sys.stderr)

    print(f"Verify assets are public: {email_asset_url('cheradip-avatar.png')}")

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
