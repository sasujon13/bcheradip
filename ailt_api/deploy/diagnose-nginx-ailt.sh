#!/usr/bin/env bash
# Diagnose why https://cheradip.com/ailt/api/health returns HTML instead of JSON.
# Run on Linux server: bash ailt_api/deploy/diagnose-nginx-ailt.sh

set -euo pipefail

echo "=== AILT API nginx diagnostic ==="
echo ""

echo "1) FastAPI on localhost:8790"
if curl -sf --max-time 3 http://127.0.0.1:8790/api/ailt/health | head -c 120; then
  echo ""
  echo "   OK  cheradip-ailt responds locally"
else
  echo "   FAIL  No response on 127.0.0.1:8790"
  echo "   Fix: sudo systemctl status cheradip-ailt"
  echo "        sudo systemctl start cheradip-ailt"
  echo "        journalctl -u cheradip-ailt -n 40 --no-pager"
fi
echo ""

echo "2) nginx config mentions /ailt/api/"
if grep -rn "ailt/api" /etc/nginx/sites-enabled /etc/nginx/conf.d /etc/nginx/snippets 2>/dev/null; then
  echo "   OK  Found /ailt/api/ in nginx"
else
  echo "   FAIL  No /ailt/api/ proxy in nginx — run:"
  echo "        sudo bash ailt_api/deploy/install-nginx-ailt-api.sh"
fi
echo ""

echo "3) HTTPS server block (listen 443) for cheradip.com"
grep -rn "listen.*443\|server_name.*cheradip" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -20 || true
echo ""

echo "4) Public URL (via Cloudflare)"
body="$(curl -sf --max-time 15 https://cheradip.com/ailt/api/health | head -c 200 || true)"
if echo "$body" | grep -q "cheradip-ailt-api"; then
  echo "   OK  Public API returns JSON"
  echo "   $body"
elif echo "$body" | grep -qi "doctype html"; then
  echo "   FAIL  Public URL still returns Angular HTML"
  echo "   The HTTPS server { } block was not patched, or nginx was not reloaded."
elif echo "$body" | grep -qi "502\|Bad Gateway\|error code"; then
  echo "   FAIL  502 Bad Gateway — nginx OK but cheradip-ailt is down"
  echo "   Fix: bash ailt_api/deploy/diagnose-ailt-db.sh"
  echo "        bash ailt_api/deploy/setup-ailt-env-from-django.sh"
  echo "        sudo systemctl restart cheradip-ailt"
else
  echo "   WARN  Unexpected response: $body"
fi
echo ""
echo "Done."
