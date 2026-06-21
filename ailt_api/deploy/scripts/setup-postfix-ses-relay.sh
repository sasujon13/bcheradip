#!/usr/bin/env bash
# Postfix → Amazon SES relay (noreply@cheradip.com via localhost:587)
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

echo "=== Amazon SES relay for Postfix ==="
echo "Guide: deploy/SMTP_AMAZON_SES.md"
echo ""

read -r -p "SES region (e.g. eu-west-1, us-east-1): " REGION
REGION="${REGION// /}"
if [[ -z "$REGION" ]]; then
  echo "Region required"
  exit 1
fi

HOST="email-smtp.${REGION}.amazonaws.com"

read -r -p "SES SMTP username (AKIA...): " SES_USER
read -r -s -p "SES SMTP password: " SES_PASS
echo

if [[ -z "$SES_USER" || -z "$SES_PASS" ]]; then
  echo "Username and password required"
  exit 1
fi

echo "=== Postfix relayhost → ${HOST} ==="
postconf -e "relayhost = [${HOST}]:587"
postconf -e "smtp_sasl_auth_enable = yes"
postconf -e "smtp_sasl_security_options = noanonymous"
postconf -e "smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd"
postconf -e "smtp_tls_security_level = encrypt"
postconf -e "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt"
postconf -e "inet_protocols = ipv4"

postconf -e "mynetworks = 127.0.0.0/8 [::1]/128"
postconf -P "submission/inet/smtpd_recipient_restrictions=permit_mynetworks,permit_sasl_authenticated,reject"
postconf -P "submission/inet/smtpd_relay_restrictions=permit_mynetworks,permit_sasl_authenticated,defer_unauth_destination"

# SES signs mail — disable local OpenDKIM milters
postconf -e "smtpd_milters ="
postconf -e "non_smtpd_milters ="
postconf -P "submission/inet/smtpd_milters=" 2>/dev/null || true
postconf -P "submission/inet/non_smtpd_milters=" 2>/dev/null || true
postconf -P "smtp/inet/smtpd_milters=" 2>/dev/null || true
postconf -P "smtp/inet/non_smtpd_milters=" 2>/dev/null || true

cat > /etc/postfix/sasl_passwd <<EOF
[${HOST}]:587 ${SES_USER}:${SES_PASS}
EOF
chmod 600 /etc/postfix/sasl_passwd
postmap /etc/postfix/sasl_passwd

systemctl restart postfix
sleep 1

echo ""
echo "=== Config ==="
postconf relayhost smtp_sasl_auth_enable
echo ""
echo "ailt_api/.env (keep localhost, no auth):"
echo "  SMTP_HOST=127.0.0.1"
echo "  SMTP_PORT=587"
echo "  SMTP_USER="
echo "  SMTP_PASSWORD="
echo "  SMTP_FROM=noreply@cheradip.com"
echo "  SMTP_USE_TLS=true"
echo ""
echo "Test: cd ailt_api && ./scripts/test_smtp.sh your@gmail.com"
echo ""
echo "Ensure in AWS SES:"
echo "  - cheradip.com identity Verified"
echo "  - Production access (or verify test recipient while in sandbox)"
echo "  - DNS SPF: v=spf1 include:amazonses.com ~all"
