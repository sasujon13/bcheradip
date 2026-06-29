#!/usr/bin/env bash
# Configure ailt_api/.env for free Gmail SMTP (Ubuntu 26 — no Postfix, no AWS)
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="$(pwd)/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

echo "=== Gmail SMTP (free) → ailt_api/.env ==="
echo "Guide: deploy/SMTP_GMAIL.md"
echo ""
echo "You need a Google App Password (not your normal Gmail password):"
echo "  https://myaccount.google.com/apppasswords"
echo ""

read -r -p "Gmail address (e.g. sashafik.me@gmail.com): " GMAIL
read -r -s -p "16-character App Password: " APP_PASS
echo

if [[ -z "$GMAIL" || -z "$APP_PASS" ]]; then
  echo "Email and app password required"
  exit 1
fi

# Remove spaces from app password (Google shows them in groups)
APP_PASS="${APP_PASS// /}"
FROM="AI Language Tutor <${GMAIL}>"

export GMAIL GMAIL_PASS="$APP_PASS" GMAIL_FROM="$FROM" ENV_PATH="$ENV_FILE"
python3 <<'PY'
import os, re
from pathlib import Path

path = Path(os.environ["ENV_PATH"])
text = path.read_text()
updates = {
    "SMTP_ENABLED": "true",
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USER": os.environ["GMAIL"],
    "SMTP_PASSWORD": os.environ["GMAIL_PASS"],
    "SMTP_FROM": os.environ["GMAIL_FROM"],
    "SMTP_USE_TLS": "true",
    "SMTP_USE_SSL": "false",
    "DEV_LOG_OTP": "false",
}
for key, val in updates.items():
    if re.search(rf"^{re.escape(key)}=", text, flags=re.M):
        text = re.sub(rf"^{re.escape(key)}=.*$", f"{key}={val}", text, flags=re.M)
    else:
        text = text.rstrip() + f"\n{key}={val}\n"
path.write_text(text)
print(f"Updated {path}")
print(f"  SMTP_USER={os.environ['GMAIL']}")
print(f"  SMTP_FROM={os.environ['GMAIL_FROM']}")
PY

echo ""
echo "Next:"
echo "  sudo systemctl restart cheradip-ailt"
echo "  ./scripts/test_smtp.sh your@gmail.com"
