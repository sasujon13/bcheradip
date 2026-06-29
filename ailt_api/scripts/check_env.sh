#!/usr/bin/env bash
# Check ailt_api .env for Brevo SMTP settings
set -euo pipefail
ENV_FILE="$(dirname "$0")/../.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi
echo "Checking $ENV_FILE ..."
issues=0
host="$(grep -E '^SMTP_HOST=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '[:space:]')"
port="$(grep -E '^SMTP_PORT=' "$ENV_FILE" | head -1 | cut -d= -f2 | tr -d '[:space:]')"
tls="$(grep -E '^SMTP_USE_TLS=' "$ENV_FILE" | head -1 | cut -d= -f2 | tr -d '[:space:]')"

if [[ "$host" != "smtp-relay.brevo.com" ]]; then
  echo "WARN: SMTP_HOST should be smtp-relay.brevo.com (got: ${host:-empty})"
  issues=$((issues + 1))
fi
if [[ "$port" != "587" ]]; then
  echo "WARN: SMTP_PORT should be 587 (got: ${port:-empty})"
  issues=$((issues + 1))
fi
if [[ "$tls" != "true" ]]; then
  echo "WARN: SMTP_USE_TLS should be true"
  issues=$((issues + 1))
fi
if [[ "$host" == "127.0.0.1" && "$port" == "25" ]]; then
  echo "WARN: local Postfix does not deliver to Gmail — use Brevo"
  issues=$((issues + 1))
fi

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

if [[ $issues -eq 0 ]]; then
  echo "OK — Brevo SMTP settings look fine"
else
  echo ""
  echo "Fix: nano $ENV_FILE  — see deploy/BREVO_EMAIL.md"
  exit 1
fi
