#!/usr/bin/env bash
# Repair /ailt/api/ nginx placement (duplicate or nested include).
# Same normalize logic as install-nginx-ailt-api.sh — safe to re-run.
#
# Run: sudo bash ailt_api/deploy/fix-nginx-duplicate-ailt-api.sh

set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE="${NGINX_SITE_FILE:-/etc/nginx/sites-available/cheradip}"

# Prefer the full installer (discover + normalize + nginx -t + start)
# when no explicit site override — keeps one code path.
if [[ -z "${NGINX_SITE_FILE:-}" ]]; then
  exec bash "${SCRIPT_DIR}/install-nginx-ailt-api.sh"
fi

if [[ ! -f "$SITE" ]]; then
  echo "Site file not found: $SITE"
  echo "Run: sudo bash ailt_api/deploy/find-nginx-site.sh"
  exit 1
fi

SNIPPET="/etc/nginx/snippets/ailt-api-location.conf"
NORMALIZE="${SCRIPT_DIR}/normalize_ailt_api_site.py"
mkdir -p /etc/nginx/snippets
cp "${SCRIPT_DIR}/snippets/ailt-api-location.conf" "$SNIPPET"

backup="${SITE}.bak.$(date +%Y%m%d%H%M%S)"
cp "$SITE" "$backup"
echo "Backup: $backup"
python3 "$NORMALIZE" "$SITE"

echo "Testing nginx..."
nginx -t
if systemctl is-active --quiet nginx; then
  systemctl reload nginx
else
  systemctl start nginx
fi
echo "OK  nginx started/reloaded"
echo ""
bash "${SCRIPT_DIR}/diagnose-nginx-ailt.sh"
