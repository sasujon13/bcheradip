#!/usr/bin/env bash
# Configure ailt_api/.env for Brevo SMTP
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="$(pwd)/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

echo "=== Brevo SMTP → ailt_api/.env ==="
echo "Guide: deploy/BREVO_EMAIL.md"
echo ""

read -r -p "Brevo SMTP Login (e.g. xxxxxxxx@smtp-brevo.com): " SMTP_USER
read -r -s -p "Brevo SMTP key (not API key): " SMTP_PASS
echo

if [[ -z "$SMTP_USER" || -z "$SMTP_PASS" ]]; then
  echo "Login and SMTP key required"
  exit 1
fi

echo "From address (verified sender in Brevo):"
echo "  1) Cheradip <noreply@cheradip.com>  (OTP — recommended)"
echo "  2) Cheradip <admin@cheradip.com>"
echo "  3) Cheradip <support@cheradip.com>"
read -r -p "Choice [1]: " FROM_CHOICE
FROM_CHOICE="${FROM_CHOICE:-1}"
case "$FROM_CHOICE" in
  2) SMTP_FROM="Cheradip <admin@cheradip.com>" ;;
  3) SMTP_FROM="Cheradip <support@cheradip.com>" ;;
  *) SMTP_FROM="Cheradip <noreply@cheradip.com>" ;;
esac

export SMTP_USER SMTP_PASS="$SMTP_PASS" SMTP_FROM ENV_PATH="$ENV_FILE"
python3 <<'PY'
import os, re
from pathlib import Path

path = Path(os.environ["ENV_PATH"])
text = path.read_text()
updates = {
    "SMTP_ENABLED": "true",
    "SMTP_HOST": "smtp-relay.brevo.com",
    "SMTP_PORT": "587",
    "SMTP_USER": os.environ["SMTP_USER"],
    "SMTP_PASSWORD": os.environ["SMTP_PASS"],
    "SMTP_FROM": os.environ["SMTP_FROM"],
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
print(f"  SMTP_HOST=smtp-relay.brevo.com")
print(f"  SMTP_FROM={os.environ['SMTP_FROM']}")
PY

echo ""
echo "Next:"
echo "  sudo systemctl restart cheradip-ailt"
echo "  ./scripts/test_smtp.sh your@gmail.com"
