#!/usr/bin/env bash
# Test Brevo SMTP + OTP email from ailt_api/.env
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VENV="${VENV:-$(dirname "$ROOT")/venv}"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Python venv not found at $VENV — set VENV=/path/to/venv"
  exit 1
fi

TO="${1:-}"
if [[ -z "$TO" ]]; then
  echo "Usage: $0 your@email.com"
  exit 1
fi

export PYTHONPATH="$ROOT"
read -r HOST PORT <<< "$("$VENV/bin/python" - <<'PY'
from app.config import settings
print(settings.smtp_host, settings.smtp_port)
PY
)"

if [[ "$HOST" != "smtp-relay.brevo.com" ]]; then
  echo ""
  echo "WARN: SMTP_HOST is '$HOST' — production should use smtp-relay.brevo.com"
  echo "Run: bash scripts/setup-brevo-env.sh"
  echo "See: deploy/BREVO_EMAIL.md"
  echo ""
fi

if [[ "$HOST" == "127.0.0.1" || "$HOST" == "localhost" ]] && [[ "$PORT" == "25" ]]; then
  echo "FAILED: local Postfix port 25 will not reach Gmail. Use Brevo."
  exit 1
fi

MARKER="ailt-smtp-test-$(date +%s)"
"$VENV/bin/python" - <<PY
import sys
from app.config import settings
from app.services.email_service import send_otp_email

print("SMTP:", settings.smtp_host, "port:", settings.smtp_port)
print("User:", settings.smtp_user or "(none)")
print("From:", settings.smtp_from)
print("TLS:", settings.smtp_use_tls, "SSL:", settings.smtp_use_ssl)
if settings.dev_log_otp:
    print("WARN: DEV_LOG_OTP=true — set false in production")
try:
    send_otp_email(to="${TO}", purpose="SMTP test ${MARKER}", code="123456")
except RuntimeError as exc:
    print("FAILED:", exc, file=sys.stderr)
    sys.exit(1)
print("OK — sent via Brevo. Check inbox + spam for ${TO}")
PY
