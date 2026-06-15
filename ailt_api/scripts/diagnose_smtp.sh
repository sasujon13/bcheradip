#!/usr/bin/env bash
# Diagnose Postfix + suggest ailt_api .env for noreply@cheradip.com
set -euo pipefail

echo "=== Postfix / OpenDKIM ==="
systemctl is-active postfix 2>/dev/null || echo "postfix: not active"
systemctl is-active opendkim 2>/dev/null || echo "opendkim: not active"

echo ""
echo "=== Listening ports ==="
ss -tlnp 2>/dev/null | grep -E ':25 |:587 |:8891 ' || echo "No SMTP/DKIM ports"

echo ""
echo "=== SASL users (SMTP_USER) ==="
if command -v sasldblistusers2 >/dev/null 2>&1; then
  sudo sasldblistusers2 2>/dev/null || echo "(run with sudo)"
else
  echo "Install: sudo apt install sasl2-bin"
fi

echo ""
echo "=== DNS (cheradip.com mail) ==="
for q in "mail.cheradip.com A" "cheradip.com MX" "mail._domainkey.cheradip.com TXT" "cheradip.com TXT"; do
  echo -n "  $q: "
  dig +short $q 2>/dev/null | head -1 || echo "?"
done

echo ""
echo "=== Recommended ailt_api/.env ==="
echo "SMTP_ENABLED=true"
echo "SMTP_HOST=127.0.0.1"
echo "SMTP_PORT=587"
echo "SMTP_USER=admin"
echo "SMTP_PASSWORD=<from setup-smtp-admin-user.sh>"
echo "SMTP_FROM=noreply@cheradip.com"
echo "SMTP_USE_TLS=true"
echo "SMTP_USE_SSL=false"
echo ""
echo "Guide: deploy/MAIL_NOREPLY_CHERADIP.md"
echo ""
if ss -tlnp 2>/dev/null | grep -q ':587 '; then
  echo "Port 587 OK. Test: ./scripts/test_smtp.sh your@gmail.com"
else
  echo "Fix 587: sudo bash deploy/scripts/fix-postfix-587.sh"
fi
