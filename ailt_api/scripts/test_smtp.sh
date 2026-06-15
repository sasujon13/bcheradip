#!/usr/bin/env bash
# Test SMTP + OTP email from ailt_api/.env (run on Linux after deploy)
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
"$VENV/bin/python" - <<PY
from app.config import settings
from app.services.email_service import send_otp_email

print("SMTP host:", settings.smtp_host, "port:", settings.smtp_port)
print("From:", settings.smtp_from)
print("TLS:", settings.smtp_use_tls, "SSL:", settings.smtp_use_ssl)
send_otp_email(to="${TO}", purpose="SMTP test", code="123456")
print("OK — check inbox (and spam) for", "${TO}")
PY
