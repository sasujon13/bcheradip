#!/usr/bin/env bash
# One-time: merge Django DB credentials into ailt_api/.env (keeps existing SMTP lines).
# Run on server from bcheradip repo root:
#   bash ailt_api/deploy/setup-ailt-env-from-django.sh
#
# Does NOT print passwords. Review .env after running.

set -euo pipefail

ROOT="${ROOT:-/home/sasha/apps/cheradip/bcheradip}"
DJANGO_ENV="$ROOT/.env"
AILT_ENV="$ROOT/ailt_api/.env"
EXAMPLE="$ROOT/ailt_api/.env.production.example"

if [[ ! -f "$DJANGO_ENV" ]]; then
  echo "Missing Django .env: $DJANGO_ENV"
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$DJANGO_ENV"
set +a

DB_USER="${DATABASE_USER:-cheradip_cheradip}"
DB_PASS="${DATABASE_PASSWORD:-}"
DB_HOST="${DATABASE_HOST:-127.0.0.1}"
DB_PORT="${DATABASE_PORT:-3306}"
DB_NAME="ailanguagetutor"

if [[ -z "$DB_PASS" ]]; then
  echo "DATABASE_PASSWORD empty in $DJANGO_ENV — set it first."
  exit 1
fi

if [[ ! -f "$AILT_ENV" ]]; then
  cp "$EXAMPLE" "$AILT_ENV"
  echo "Created $AILT_ENV from .env.production.example"
fi

# URL-encode password for SQLAlchemy URL (basic: @ : / etc.)
encode() {
  python3 -c "import urllib.parse,sys; print(urllib.parse.quote_plus(sys.argv[1]))" "$1"
}
ENC_PASS="$(encode "$DB_PASS")"
DATABASE_URL="mysql+pymysql://${DB_USER}:${ENC_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}?charset=utf8mb4"

if grep -q "^DATABASE_URL=" "$AILT_ENV"; then
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DATABASE_URL}|" "$AILT_ENV"
else
  echo "DATABASE_URL=${DATABASE_URL}" >> "$AILT_ENV"
fi

for key in GUEST_AI_LIMIT PUBLIC_BASE_URL HOST PORT; do
  if ! grep -q "^${key}=" "$AILT_ENV" 2>/dev/null; then
    case "$key" in
      GUEST_AI_LIMIT) echo "GUEST_AI_LIMIT=99999999" >> "$AILT_ENV" ;;
      PUBLIC_BASE_URL) echo "PUBLIC_BASE_URL=https://cheradip.com/ailt/api" >> "$AILT_ENV" ;;
      HOST) echo "HOST=127.0.0.1" >> "$AILT_ENV" ;;
      PORT) echo "PORT=8790" >> "$AILT_ENV" ;;
    esac
  fi
done

chmod 600 "$AILT_ENV"
echo "Updated DATABASE_URL in $AILT_ENV (password not shown)."
echo "Restart: sudo systemctl restart cheradip-ailt"
echo "Test:    curl -s http://127.0.0.1:8790/api/ailt/health | head -c 200"
