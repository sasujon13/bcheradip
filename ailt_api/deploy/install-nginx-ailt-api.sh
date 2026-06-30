#!/usr/bin/env bash
# Install /ailt/api/ nginx proxy on cheradip.com (Ubuntu).
# Run on Linux server: sudo bash ailt_api/deploy/install-nginx-ailt-api.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNIPPET_SRC="${SCRIPT_DIR}/snippets/ailt-api-location.conf"
SNIPPET_DST="/etc/nginx/snippets/ailt-api-location.conf"
INCLUDE_LINE='    include snippets/ailt-api-location.conf;'

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

if [[ ! -f "$SNIPPET_SRC" ]]; then
  echo "Missing $SNIPPET_SRC"
  exit 1
fi

echo "Installing snippet -> $SNIPPET_DST"
mkdir -p /etc/nginx/snippets
cp "$SNIPPET_SRC" "$SNIPPET_DST"

echo "Searching HTTPS (443) server blocks for cheradip.com..."
mapfile -t SITE_FILES < <(
  grep -rl "cheradip.com" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | while read -r f; do
    real="$(readlink -f "$f" 2>/dev/null || echo "$f")"
    if grep -qE "listen[[:space:]]+443|ssl" "$real" 2>/dev/null; then
      echo "$real"
    fi
  done | sort -u
)

if [[ ${#SITE_FILES[@]} -eq 0 ]]; then
  echo "No HTTPS cheradip.com block found; falling back to any cheradip.com file..."
  mapfile -t SITE_FILES < <(grep -rl "cheradip.com" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null || true)
fi

if [[ ${#SITE_FILES[@]} -eq 0 ]]; then
  echo "ERROR: No nginx config mentions cheradip.com."
  echo "Run: sudo grep -r cheradip.com /etc/nginx/"
  exit 1
fi

patched=0
for real in "${SITE_FILES[@]}"; do
  if grep -q "ailt/api" "$real" 2>/dev/null; then
    echo "OK  $real already has /ailt/api/ proxy"
    patched=1
    continue
  fi
  if grep -qF "include snippets/ailt-api-location.conf" "$real" 2>/dev/null; then
    echo "OK  $real already includes ailt-api snippet"
    patched=1
    continue
  fi

  echo "Patching $real ..."
  backup="${real}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$real" "$backup"
  echo "  backup: $backup"

  # Insert include inside server { }, before first "location /" (Angular catch-all)
  awk -v inc="$INCLUDE_LINE" '
    BEGIN { in_server=0; done=0 }
    /^[[:space:]]*server[[:space:]]*\{/ { in_server=1 }
    in_server && /location[[:space:]]+\/[[:space:]]*\{/ && !done {
      print inc
      done=1
    }
    { print }
    in_server && /^[[:space:]]*\}/ {
      if (!done) {
        print inc
        done=1
      }
      in_server=0
    }
  ' "$backup" > "${real}.tmp"
  mv "${real}.tmp" "$real"
  echo "  added include before location / {"
  patched=1
done

if [[ $patched -eq 0 ]]; then
  echo "ERROR: Could not patch any site file."
  exit 1
fi

echo "Testing nginx config..."
nginx -t

echo "Reloading nginx..."
systemctl reload nginx

echo ""
bash "${SCRIPT_DIR}/diagnose-nginx-ailt.sh"
