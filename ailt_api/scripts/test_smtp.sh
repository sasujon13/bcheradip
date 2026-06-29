#!/usr/bin/env bash
# Test Brevo SMTP + branded OTP email from ailt_api/.env
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
exec "$VENV/bin/python" "$ROOT/scripts/test_smtp.py" "$TO" \
  --save-preview "$ROOT/deploy/email-preview-otp.out.html"
