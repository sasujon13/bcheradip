#!/usr/bin/env bash
# Set Postfix SASL password for admin + update ailt_api/.env (same password)
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="$(pwd)/.env"
REALM="${SMTP_REALM:-mail.cheradip.com}"
USER="${SMTP_USER:-admin}"

if [[ $EUID -ne 0 ]]; then
  echo "Run: sudo bash $0"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

read -r -s -p "New password for ${USER}@${REALM}: " PW1
echo
read -r -s -p "Confirm password: " PW2
echo
if [[ "$PW1" != "$PW2" ]]; then
  echo "Passwords do not match"
  exit 1
fi

apt-get install -y sasl2-bin libsasl2-modules >/dev/null 2>&1 || true
printf '%s\n' "$PW1" | saslpasswd2 -c -p -u "${REALM}" "${USER}"
chown postfix:postfix /etc/sasldb2
chmod 660 /etc/sasldb2

SASL_PW="$PW1" ENV_PATH="$ENV_FILE" SMTP_USER="$USER" python3 <<'PY'
import os, re
from pathlib import Path

pw = os.environ["SASL_PW"]
user = os.environ["SMTP_USER"]
path = Path(os.environ["ENV_PATH"])
text = path.read_text()
text = re.sub(r"^SMTP_PASSWORD=.*$", f"SMTP_PASSWORD={pw}", text, flags=re.M)
text = re.sub(r"^SMTP_USER=.*$", f"SMTP_USER={user}", text, flags=re.M)
text = re.sub(r"^SMTP_USE_TLS=.*$", "SMTP_USE_TLS=true", text, flags=re.M)
text = re.sub(r"^SMTP_PORT=.*$", "SMTP_PORT=587", text, flags=re.M)
path.write_text(text)
print(f"Updated {path}")
PY

echo ""
echo "SASL users:"
sasldblistusers2
echo ""
echo "Test: ./scripts/test_smtp.sh your@gmail.com"
