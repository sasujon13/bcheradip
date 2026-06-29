#!/usr/bin/env bash
# Configure ailt_api/.env for Amazon SES (Ubuntu 26 — direct SMTP, no Postfix)
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="$(pwd)/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy from .env.production.example first"
  exit 1
fi

echo "=== Amazon SES → ailt_api/.env ==="
echo "Guide: deploy/SES_UBUNTU26.md"
echo ""

read -r -p "SES region (e.g. eu-west-1, ap-south-1): " REGION
REGION="${REGION// /}"
if [[ -z "$REGION" ]]; then
  echo "Region required"
  exit 1
fi

HOST="email-smtp.${REGION}.amazonaws.com"
read -r -p "SES SMTP username (AKIA...): " SES_USER
read -r -s -p "SES SMTP password: " SES_PASS
echo

if [[ -z "$SES_USER" || -z "$SES_PASS" ]]; then
  echo "Username and password required"
  exit 1
fi

FROM="${SMTP_FROM:-noreply@cheradip.com}"
read -r -p "From address [$FROM]: " FROM_IN
FROM="${FROM_IN:-$FROM}"

export SES_HOST="$HOST" SES_USER="$SES_USER" SES_PASS="$SES_PASS" SES_FROM="$FROM" ENV_PATH="$ENV_FILE"
python3 <<'PY'
import os, re
from pathlib import Path

path = Path(os.environ["ENV_PATH"])
text = path.read_text()
updates = {
    "SMTP_ENABLED": "true",
    "SMTP_HOST": os.environ["SES_HOST"],
    "SMTP_PORT": "587",
    "SMTP_USER": os.environ["SES_USER"],
    "SMTP_PASSWORD": os.environ["SES_PASS"],
    "SMTP_FROM": os.environ["SES_FROM"],
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
print(f"  SMTP_HOST={os.environ['SES_HOST']}")
print(f"  SMTP_FROM={os.environ['SES_FROM']}")
PY

echo ""
echo "Next:"
echo "  sudo systemctl restart cheradip-ailt"
echo "  ./scripts/test_smtp.sh your@gmail.com"
