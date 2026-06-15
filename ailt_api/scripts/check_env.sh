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
if [[ $issues -eq 0 ]]; then
  echo "OK — boolean flags look fine"
else
  echo ""
  echo "Fix with: nano $ENV_FILE"
  exit 1
fi
