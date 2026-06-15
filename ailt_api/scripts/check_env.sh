#!/usr/bin/env bash
# Print .env lines that look like typos (common manual edit mistakes)
set -euo pipefail
ENV_FILE="$(dirname "$0")/../.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi
echo "Checking $ENV_FILE ..."
issues=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" =~ = ]] || continue
  key="${line%%=*}"
  val="${line#*=}"
  val="$(echo "$val" | tr -d '[:space:]')"
  case "$key" in
    DEV_LOG_OTP|SMTP_ENABLED|SMTP_USE_TLS|SMTP_USE_SSL|TRANSLATE_API_RESPONSES)
      if [[ "$val" != "true" && "$val" != "false" ]]; then
        echo "WARN: $key=$val  (use exactly true or false)"
        issues=$((issues + 1))
      fi
      ;;
  esac
done < "$ENV_FILE"
port="$(grep -E '^SMTP_PORT=' "$ENV_FILE" | head -1 | cut -d= -f2 | tr -d '[:space:]')"
tls="$(grep -E '^SMTP_USE_TLS=' "$ENV_FILE" | head -1 | cut -d= -f2 | tr -d '[:space:]')"
if [[ "$port" == "587" && "$tls" == "false" ]]; then
  echo "WARN: SMTP_PORT=587 requires SMTP_USE_TLS=true (Postfix AUTH needs STARTTLS)"
  issues=$((issues + 1))
fi
if [[ "$port" == "25" ]]; then
  echo "WARN: SMTP_PORT=25 will not deliver to Gmail/Yahoo — use 587"
  issues=$((issues + 1))
fi

if [[ $issues -eq 0 ]]; then
  echo "OK — SMTP settings look fine"
else
  echo ""
  echo "Fix with: nano $ENV_FILE"
  exit 1
fi
