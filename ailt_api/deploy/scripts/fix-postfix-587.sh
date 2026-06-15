#!/usr/bin/env bash
# Enable Postfix submission on 127.0.0.1:587 + OpenDKIM milter
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

DOMAIN=cheradip.com
HOSTNAME=mail.cheradip.com

echo "=== Starting postfix ==="
systemctl enable postfix
systemctl start postfix

echo "=== Loopback only (safe for VPS) ==="
postconf -e "inet_interfaces = loopback-only"
postconf -e "myhostname = ${HOSTNAME}"
postconf -e "mydomain = ${DOMAIN}"
postconf -e "myorigin = \$mydomain"

echo "=== Enable submission on 587 ==="
postconf -M submission/inet="submission inet n       -       y       -       -       smtpd" 2>/dev/null || true
postconf -P "submission/inet/syslog_name=postfix/submission"
postconf -P "submission/inet/smtpd_tls_security_level=encrypt"
postconf -P "submission/inet/smtpd_sasl_auth_enable=yes"
postconf -P "submission/inet/smtpd_sasl_security_options=noanonymous"
postconf -P "submission/inet/broken_sasl_auth_clients=yes"
postconf -P "submission/inet/smtpd_sasl_type=cyrus"
postconf -P "submission/inet/smtpd_sasl_path=sasldb"
postconf -P "submission/inet/smtpd_recipient_restrictions=permit_sasl_authenticated,reject"
postconf -P "submission/inet/smtpd_sasl_local_domain=${HOSTNAME}"

mkdir -p /etc/postfix/sasl
if [[ ! -f /etc/postfix/sasl/smtpd.conf ]]; then
  cat > /etc/postfix/sasl/smtpd.conf <<'EOF'
pwcheck_method: auxprop
auxprop_plugin: sasldb
mech_list: PLAIN LOGIN
EOF
fi

bash "${SCRIPT_DIR}/fix-opendkim.sh"

systemctl restart postfix
sleep 1

echo ""
echo "=== Ports after restart ==="
ss -tlnp | grep -E ':25 |:587 |:8891 ' || true

if ! ss -tlnp | grep -q ':587 '; then
  echo ""
  echo "ERROR: 587 not listening — check: journalctl -u postfix -n 30"
  exit 1
fi

if ! sasldblistusers2 2>/dev/null | grep -q '@'; then
  echo ""
  echo "No SASL users — run: sudo bash deploy/scripts/setup-smtp-admin-user.sh"
fi

echo ""
echo "Use ailt_api/.env: SMTP_PORT=587 SMTP_USER=admin SMTP_FROM=noreply@cheradip.com"
echo "Do NOT use SMTP_PORT=25 — Gmail rejects direct VPS send (550 5.7.1)"
echo ""
echo "Done. Run: bash scripts/diagnose_smtp.sh"
