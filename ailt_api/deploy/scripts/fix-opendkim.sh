#!/usr/bin/env bash
# Fix common OpenDKIM failures on Ubuntu/Debian + wire Postfix milter
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

DOMAIN=cheradip.com
SELECTOR=mail
KEY_DIR="/etc/opendkim/keys/${DOMAIN}"

echo "=== Install OpenDKIM if missing ==="
export DEBIAN_FRONTEND=noninteractive
apt-get install -y opendkim opendkim-tools 2>/dev/null || true

echo "=== Stop stale OpenDKIM ==="
systemctl stop opendkim 2>/dev/null || true
pkill -x opendkim 2>/dev/null || true
sleep 1

echo "=== DKIM keys ==="
mkdir -p "${KEY_DIR}"
if [[ ! -f "${KEY_DIR}/${SELECTOR}.private" ]]; then
  opendkim-genkey -b 2048 -d "${DOMAIN}" -D "${KEY_DIR}" -s "${SELECTOR}" -v
fi
chown -R opendkim:opendkim /etc/opendkim
chmod 700 "${KEY_DIR}"
chmod 600 "${KEY_DIR}/${SELECTOR}.private" 2>/dev/null || true

echo "=== opendkim.conf (systemd: Background no, socket via /etc/default/opendkim) ==="
cat > /etc/opendkim.conf <<EOF
Syslog                  yes
LogWhy                  yes
UMask                   007
UserID                  opendkim:opendkim
Mode                    sv
Canonicalization        relaxed/simple
SubDomains              no
AutoRestart             yes
AutoRestartRate         10/1M
Background              no
DNSTimeout              5
SignatureAlgorithm      rsa-sha256
Domain                  ${DOMAIN}
KeyFile                 ${KEY_DIR}/${SELECTOR}.private
Selector                ${SELECTOR}
EOF

echo "=== /etc/default/opendkim ==="
cat > /etc/default/opendkim <<'EOF'
SOCKET=inet:8891@localhost
PIDFILE=/run/opendkim/opendkim.pid
EOF
mkdir -p /run/opendkim
chown opendkim:opendkim /run/opendkim

echo "=== Postfix milter (587 + smtp) ==="
postconf -e 'milter_default_action = accept'
postconf -e 'milter_protocol = 6'
postconf -e 'smtpd_milters = inet:localhost:8891'
postconf -e 'non_smtpd_milters = inet:localhost:8891'

for svc in submission/inet smtp/inet; do
  postconf -P "${svc}/milter_protocol=6" 2>/dev/null || true
  postconf -P "${svc}/milter_default_action=accept" 2>/dev/null || true
  postconf -P "${svc}/smtpd_milters=inet:localhost:8891" 2>/dev/null || true
  postconf -P "${svc}/non_smtpd_milters=inet:localhost:8891" 2>/dev/null || true
done

systemctl enable opendkim
systemctl start opendkim
sleep 2
if ! systemctl is-active --quiet opendkim; then
  echo "OpenDKIM failed — last log lines:"
  journalctl -u opendkim -n 20 --no-pager || true
  exit 1
fi
systemctl restart postfix

echo ""
echo "=== Status ==="
systemctl is-active opendkim postfix
ss -tlnp | grep 8891 || echo "WARN: OpenDKIM not listening on 8891"

echo ""
echo "=== Add this DNS TXT (mail._domainkey) ==="
cat "${KEY_DIR}/${SELECTOR}.txt"
echo ""
echo "Then: ./scripts/test_smtp.sh your@gmail.com"
