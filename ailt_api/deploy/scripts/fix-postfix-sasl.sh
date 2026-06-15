#!/usr/bin/env bash
# Fix Postfix SASL auth on port 587 (sasldb password always failing)
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

HOSTNAME=mail.cheradip.com

echo "=== SASL config files ==="
mkdir -p /etc/postfix/sasl
cat > /etc/postfix/sasl/smtpd.conf <<'EOF'
pwcheck_method: auxprop
auxprop_plugin: sasldb
mech_list: PLAIN LOGIN
EOF
cp -f /etc/postfix/sasl/smtpd.conf /etc/postfix/sasl/sasldb.conf

echo "=== Postfix submission SASL ==="
postconf -P "submission/inet/smtpd_sasl_auth_enable=yes"
postconf -P "submission/inet/smtpd_sasl_type=cyrus"
postconf -P "submission/inet/smtpd_sasl_path=smtpd"
postconf -P "submission/inet/cyrus_sasl_config_path=/etc/postfix/sasl"
postconf -P "submission/inet/smtpd_sasl_security_options=noanonymous"
postconf -P "submission/inet/broken_sasl_auth_clients=yes"
postconf -P "submission/inet/smtpd_sasl_local_domain=${HOSTNAME}"

chown postfix:postfix /etc/sasldb2 2>/dev/null || true
chmod 660 /etc/sasldb2 2>/dev/null || true

systemctl restart postfix
sleep 1

echo ""
echo "=== Config ==="
postconf -P | grep -E 'submission/inet/smtpd_sasl|submission/inet/cyrus'
echo ""
ls -la /etc/postfix/sasl/
echo ""
echo "If auth still fails, reset password:"
echo "  sudo bash deploy/scripts/sync-smtp-password.sh"
echo "  or: sudo bash deploy/scripts/setup-smtp-admin-user.sh"
