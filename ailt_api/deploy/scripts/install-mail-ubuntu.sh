#!/usr/bin/env bash
# Postfix + OpenDKIM bootstrap for mail.cheradip.com (Ubuntu/Debian)
# Run on the VPS: sudo bash install-mail-ubuntu.sh
#
# BEFORE running: add DNS A record mail.cheradip.com -> this server's IP
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo"
  exit 1
fi

DOMAIN=cheradip.com
HOSTNAME=mail.cheradip.com
SELECTOR=mail

echo "=== Installing Postfix, OpenDKIM, SASL ==="
export DEBIAN_FRONTEND=noninteractive
debconf-set-selections <<< "postfix postfix/mailname string ${DOMAIN}"
debconf-set-selections <<< "postfix postfix/main_mailer_type string 'Internet Site'"
apt-get update -qq
apt-get install -y postfix opendkim opendkim-tools mailutils \
  libsasl2-modules sasl2-bin libssl-dev

echo "=== Postfix base config ==="
postconf -e "myhostname = ${HOSTNAME}"
postconf -e "mydomain = ${DOMAIN}"
postconf -e "myorigin = \$mydomain"
postconf -e "inet_interfaces = loopback-only"
postconf -e "mydestination = \$myhostname, localhost.\$mydomain, localhost"
postconf -e "smtpd_tls_security_level = may"
postconf -e "smtp_tls_security_level = may"

echo "=== Submission port 587 + SASL (sasldb) ==="
postconf -M submission/inet="submission inet n       -       y       -       -       smtpd"
postconf -P "submission/inet/syslog_name=postfix/submission"
postconf -P "submission/inet/smtpd_tls_security_level=encrypt"
postconf -P "submission/inet/smtpd_sasl_auth_enable=yes"
postconf -P "submission/inet/smtpd_sasl_security_options=noanonymous"
postconf -P "submission/inet/broken_sasl_auth_clients=yes"
postconf -P "submission/inet/smtpd_sasl_type=cyrus"
postconf -P "submission/inet/smtpd_sasl_path=smtpd"
postconf -P "submission/inet/cyrus_sasl_config_path=/etc/postfix/sasl"
postconf -P "submission/inet/smtpd_recipient_restrictions=permit_sasl_authenticated,reject"
postconf -P "submission/inet/smtpd_sasl_local_domain=${HOSTNAME}"
postconf -P "submission/inet/milter_protocol=6"
postconf -P "submission/inet/milter_default_action=accept"
postconf -P "submission/inet/smtpd_milters=inet:localhost:8891"
postconf -P "submission/inet/non_smtpd_milters=inet:localhost:8891"

mkdir -p /etc/postfix/sasl
cat > /etc/postfix/sasl/smtpd.conf <<'EOF'
pwcheck_method: auxprop
auxprop_plugin: sasldb
mech_list: PLAIN LOGIN
EOF
cp -f /etc/postfix/sasl/smtpd.conf /etc/postfix/sasl/sasldb.conf

echo "=== Create SMTP user 'admin' (you will be prompted for password) ==="
echo "Use this password as SMTP_PASSWORD in ailt_api/.env (SMTP_USER=admin)"
saslpasswd2 -c -u "${HOSTNAME}" admin
chown postfix:postfix /etc/sasldb2
chmod 660 /etc/sasldb2

cat > /etc/postfix/generic <<EOF
admin@${HOSTNAME} noreply@${DOMAIN}
noreply@${HOSTNAME} noreply@${DOMAIN}
@${HOSTNAME} @${DOMAIN}
EOF
postmap /etc/postfix/generic
postconf -e 'smtp_generic_maps = hash:/etc/postfix/generic'

echo "=== OpenDKIM ==="
mkdir -p "/etc/opendkim/keys/${DOMAIN}"
opendkim-genkey -b 2048 -d "${DOMAIN}" -D "/etc/opendkim/keys/${DOMAIN}" -s "${SELECTOR}" -v
chown -R opendkim:opendkim /etc/opendkim

cat > /etc/opendkim.conf <<EOF
Syslog yes
LogWhy yes
UMask 007
UserID opendkim:opendkim
Canonicalization relaxed/simple
Mode sv
SubDomains no
AutoRestart yes
AutoRestartRate 10/1M
Background no
DNSTimeout 5
SignatureAlgorithm rsa-sha256
Domain ${DOMAIN}
KeyFile /etc/opendkim/keys/${DOMAIN}/${SELECTOR}.private
Selector ${SELECTOR}
EOF

cat > /etc/default/opendkim <<'EOF'
SOCKET=inet:8891@localhost
PIDFILE=/run/opendkim/opendkim.pid
EOF
mkdir -p /run/opendkim
chown opendkim:opendkim /run/opendkim

postconf -e 'milter_default_action = accept'
postconf -e 'milter_protocol = 6'
postconf -e 'smtpd_milters = inet:localhost:8891'
postconf -e 'non_smtpd_milters = inet:localhost:8891'

systemctl enable postfix opendkim
systemctl restart opendkim
systemctl restart postfix

echo ""
echo "=== DONE ==="
echo "1. Add DNS records (see deploy/MAIL_NOREPLY_CHERADIP.md)"
echo "2. DKIM TXT for mail._domainkey:"
cat "/etc/opendkim/keys/${DOMAIN}/${SELECTOR}.txt"
echo ""
echo "3. ailt_api/.env:"
echo "   SMTP_HOST=127.0.0.1"
echo "   SMTP_PORT=587"
echo "   SMTP_USER=admin"
echo "   SMTP_PASSWORD=<password you just entered>"
echo "   SMTP_FROM=noreply@${DOMAIN}"
echo "   SMTP_USE_TLS=true"
echo ""
echo "4. Test: cd ailt_api && ./scripts/test_smtp.sh your@gmail.com"
