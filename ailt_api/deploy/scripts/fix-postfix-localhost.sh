#!/usr/bin/env bash
# Allow ailt_api on 127.0.0.1:587 to send without SASL (same server, TLS still required)
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

DOMAIN=cheradip.com
HOSTNAME=mail.cheradip.com

echo "=== Trust localhost for submission ==="
postconf -e "mynetworks = 127.0.0.0/8 [::1]/128"
postconf -e "myhostname = ${HOSTNAME}"
postconf -e "mydomain = ${DOMAIN}"

postconf -M submission/inet="submission inet n       -       y       -       -       smtpd" 2>/dev/null || true
postconf -P "submission/inet/syslog_name=postfix/submission"
postconf -P "submission/inet/smtpd_tls_security_level=encrypt"
postconf -P "submission/inet/smtpd_sasl_auth_enable=yes"
postconf -P "submission/inet/smtpd_recipient_restrictions=permit_mynetworks,permit_sasl_authenticated,reject"
postconf -P "submission/inet/smtpd_relay_restrictions=permit_mynetworks,permit_sasl_authenticated,defer_unauth_destination"

mkdir -p /etc/postfix/sasl
cat > /etc/postfix/sasl/smtpd.conf <<'EOF'
pwcheck_method: auxprop
auxprop_plugin: sasldb
mech_list: PLAIN LOGIN
sasldb_path: /etc/sasldb2
EOF
cp -f /etc/postfix/sasl/smtpd.conf /etc/postfix/sasl/sasldb.conf
postconf -P "submission/inet/smtpd_sasl_type=cyrus"
postconf -P "submission/inet/smtpd_sasl_path=smtpd"
postconf -P "submission/inet/cyrus_sasl_config_path=/etc/postfix/sasl"

systemctl restart postfix
sleep 1

echo ""
echo "=== Done ==="
echo "Update ailt_api/.env (localhost needs no SASL login):"
echo "  SMTP_HOST=127.0.0.1"
echo "  SMTP_PORT=587"
echo "  SMTP_USER="
echo "  SMTP_PASSWORD="
echo "  SMTP_FROM=noreply@cheradip.com"
echo "  SMTP_USE_TLS=true"
echo ""
echo "Test: cd ailt_api && ./scripts/test_smtp.sh your@gmail.com"
