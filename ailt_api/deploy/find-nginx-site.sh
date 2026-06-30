#!/usr/bin/env bash
# Find which nginx file serves cheradip.com / /var/www/cheradip
# Run: sudo bash ailt_api/deploy/find-nginx-site.sh

set -euo pipefail

echo "=== Find nginx site for cheradip ==="
echo ""

echo "--- nginx -T (server_name, root, listen) ---"
nginx -T 2>/dev/null | grep -E "^\s+#|server_name|^\s+root |listen " | head -80 || echo "(nginx -T failed — run with sudo)"
echo ""

echo "--- grep cheradip / var/www/cheradip ---"
grep -rn "cheradip\|/var/www/cheradip" /etc/nginx/ 2>/dev/null || echo "(no matches)"
echo ""

echo "--- sites-enabled ---"
ls -la /etc/nginx/sites-enabled/ 2>/dev/null || true
echo ""

echo "--- try_files (Angular SPA) ---"
grep -rln "try_files.*index.html" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null || true
echo ""

echo "--- Recommended site file for AILT API ---"
if [[ -f /etc/nginx/sites-available/cheradip ]]; then
  echo "  /etc/nginx/sites-available/cheradip  (use this for install)"
  echo "  sudo NGINX_SITE_FILE=/etc/nginx/sites-available/cheradip bash ailt_api/deploy/install-nginx-ailt-api.sh"
else
  echo "  (no /etc/nginx/sites-available/cheradip — pick a path from grep above)"
fi
echo ""
if command -v apache2ctl >/dev/null 2>&1; then
  apache2ctl -S 2>/dev/null | head -30 || true
  grep -rn "cheradip\|/var/www/cheradip" /etc/apache2/ 2>/dev/null | head -20 || true
elif command -v httpd >/dev/null 2>&1; then
  httpd -S 2>/dev/null | head -20 || true
else
  echo "apache not installed"
fi
