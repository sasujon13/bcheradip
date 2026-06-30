#!/usr/bin/env bash
# Install /ailt/api/ nginx proxy on cheradip.com (Ubuntu).
# Run on Linux server: sudo bash ailt_api/deploy/install-nginx-ailt-api.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNIPPET_SRC="${SCRIPT_DIR}/nginx-ailt-api.conf"
SNIPPET_DST="/etc/nginx/snippets/ailt-api-location.conf"
INCLUDE_LINE='include snippets/ailt-api-location.conf;'

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

echo "Searching for cheradip.com server block..."
mapfile -t SITE_FILES < <(grep -rl "cheradip.com" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null || true)

if [[ ${#SITE_FILES[@]} -eq 0 ]]; then
  echo "ERROR: No nginx config mentions cheradip.com."
  echo "Find your site file manually — see deploy/NGINX_INSTALL.md"
  exit 1
fi

patched=0
for site in "${SITE_FILES[@]}"; do
  real="$(readlink -f "$site" 2>/dev/null || echo "$site")"
  if grep -q "ailt/api" "$real" 2>/dev/null; then
    echo "OK  $real already has /ailt/api/ proxy"
    patched=1
    continue
  fi
  if grep -qF "$INCLUDE_LINE" "$real" 2>/dev/null; then
    echo "OK  $real already includes ailt-api snippet"
    patched=1
    continue
  fi

  echo "Patching $real ..."
  backup="${real}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$real" "$backup"
  echo "  backup: $backup"

  awk -v inc="$INCLUDE_LINE" '
    BEGIN { done=0 }
    /location[[:space:]]+\// && !done {
      print "    " inc
      done=1
    }
    { print }
    END {
      if (!done) {
        print "    " inc
      }
    }
  ' "$backup" > "${real}.tmp"
  mv "${real}.tmp" "$real"
  echo "  added: $INCLUDE_LINE (before first location / or at end of file)"
  patched=1
done

echo "Testing nginx config..."
nginx -t

echo "Reloading nginx..."
systemctl reload nginx

echo ""
echo "Local API:"
curl -sf http://127.0.0.1:8790/api/ailt/health | head -c 200 || echo "(cheradip-ailt not responding on 8790 — run: systemctl start cheradip-ailt)"
echo ""
echo ""
echo "Public API:"
curl -sf https://cheradip.com/ailt/api/health | head -c 200 || echo "(still failing — check SSL server block was patched)"
echo ""
echo "Done. See deploy/NGINX_INSTALL.md if public URL still returns HTML."
