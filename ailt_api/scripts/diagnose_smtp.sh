#!/usr/bin/env bash
# Diagnose Brevo SMTP settings for ailt_api
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== ailt_api .env (Brevo) ==="
if [[ -f .env ]]; then
  grep -E '^SMTP_|^DEV_LOG' .env | sed 's/SMTP_PASSWORD=.*/SMTP_PASSWORD=***/' || true
else
  echo "Missing .env"
fi

echo ""
echo "=== Expected production ==="
echo "SMTP_HOST=smtp-relay.brevo.com"
echo "SMTP_PORT=587"
echo "SMTP_USER=<login@smtp-brevo.com>"
echo "SMTP_FROM=Cheradip <noreply@cheradip.com>"
echo "SMTP_USE_TLS=true"
echo ""
echo "Guide: deploy/BREVO_EMAIL.md"
echo "Setup: bash scripts/setup-brevo-env.sh"
echo "Test:  ./scripts/test_smtp.sh your@gmail.com"
