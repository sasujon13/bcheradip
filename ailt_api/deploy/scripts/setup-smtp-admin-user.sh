#!/usr/bin/env bash
# Create or reset Postfix SASL user 'admin' for ailt_api (From: noreply@cheradip.com)
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

HOSTNAME=mail.cheradip.com

apt-get install -y sasl2-bin libsasl2-modules 2>/dev/null || true

echo "Creating SASL user 'admin' for ${HOSTNAME}"
echo "Use this password as SMTP_PASSWORD in ailt_api/.env (SMTP_USER=admin)"
saslpasswd2 -c -u "${HOSTNAME}" admin

chown postfix:postfix /etc/sasldb2
chmod 660 /etc/sasldb2

echo ""
echo "SASL users:"
sasldblistusers2
echo ""
echo "ailt_api/.env:"
echo "  SMTP_HOST=127.0.0.1"
echo "  SMTP_PORT=587"
echo "  SMTP_USER=admin"
echo "  SMTP_PASSWORD=<password you just entered>"
echo "  SMTP_FROM=noreply@cheradip.com"
echo "  SMTP_USE_TLS=true"
