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
HOST=$("$VENV/bin/python" - <<'PY'
from app.config import settings
print(settings.smtp_host)
PY
)
PORT=$("$VENV/bin/python" - <<'PY'
from app.config import settings
print(settings.smtp_port)
PY
)

if [[ "$HOST" == "127.0.0.1" || "$HOST" == "localhost" ]] && [[ "$PORT" == "25" ]]; then
  echo ""
  echo "FAILED: SMTP_PORT=25 on localhost."
  echo "Gmail/Yahoo reject direct VPS delivery (550 5.7.1)."
  echo "Use SMTP_PORT=587 SMTP_USER=admin — deploy/MAIL_NOREPLY_CHERADIP.md"
  exit 1
fi

MARKER="ailt-smtp-test-$(date +%s)"
"$VENV/bin/python" - <<PY
from app.config import settings
from app.services.email_service import send_otp_email

print("SMTP:", settings.smtp_host, "port:", settings.smtp_port)
print("User:", settings.smtp_user or "(none)")
print("From:", settings.smtp_from)
print("TLS:", settings.smtp_use_tls, "SSL:", settings.smtp_use_ssl)
send_otp_email(to="${TO}", purpose="SMTP test ${MARKER}", code="123456")
print("Handed off to SMTP — checking delivery...")
PY

sleep 4
if [[ -r /var/log/mail.log ]]; then
  RECENT=$(sudo tail -40 /var/log/mail.log 2>/dev/null || tail -40 /var/log/mail.log 2>/dev/null || true)
  if echo "$RECENT" | grep -qE 'status=bounced.*NotAuthorizedError|not authorized to send email directly'; then
    echo ""
    echo "FAILED: Remote provider rejected direct VPS send (550 5.7.1)."
    echo "Complete DNS + DKIM + PTR — deploy/MAIL_NOREPLY_CHERADIP.md"
    echo "$RECENT" | grep -E 'status=bounced|said:' | tail -3
    exit 1
  fi
  if echo "$RECENT" | grep -q 'status=sent'; then
    echo "OK — remote server accepted mail. Check inbox + spam for ${TO}"
    exit 0
  fi
  if echo "$RECENT" | grep -q 'status=bounced'; then
    echo ""
    echo "FAILED: message bounced:"
    echo "$RECENT" | grep -E 'status=bounced|said:' | tail -5
    exit 1
  fi
fi

echo "OK — sent via ${HOST}:${PORT}. If no mail in ~2 min:"
echo "  sudo tail -30 /var/log/mail.log"
echo "  ./scripts/diagnose_smtp.sh"
