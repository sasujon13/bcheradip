#!/usr/bin/env bash
# Fix common OpenDKIM failures on Ubuntu/Debian + wire Postfix milter
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

DOMAIN=cheradip.com
HOSTNAME=mail.cheradip.com
SELECTOR=mail
KEY_DIR="/etc/opendkim/keys/${DOMAIN}"

echo "=== Install OpenDKIM if missing ==="
export DEBIAN_FRONTEND=noninteractive
apt-get install -y opendkim opendkim-tools 2>/dev/null || true

echo "=== DKIM keys ==="
mkdir -p "${KEY_DIR}"
if [[ ! -f "${KEY_DIR}/${SELECTOR}.private" ]]; then
  opendkim-genkey -b 2048 -d "${DOMAIN}" -D "${KEY_DIR}" -s "${SELECTOR}" -v
fi
chown -R opendkim:opendkim /etc/opendkim
chmod 700 "${KEY_DIR}"
chmod 600 "${KEY_DIR}/${SELECTOR}.private" 2>/dev/null || true

echo "=== opendkim.conf ==="
cat > /etc/opendkim.conf <<EOF
Syslog                  yes
LogWhy                  yes
UMask                   007
UserID                  opendkim
Mode                    sv
Canonicalization        relaxed/simple
SubDomains              no
AutoRestart             yes
AutoRestartRate         10/1M
Background              yes
DNSTimeout              5
SignatureAlgorithm      rsa-sha256
Domain                  ${DOMAIN}
KeyFile                 ${KEY_DIR}/${SELECTOR}.private
Selector                ${SELECTOR}
Socket                  inet:8891@localhost
EOF

echo "=== /etc/default/opendkim ==="
if [[ -f /etc/default/opendkim ]]; then
  if grep -q '^SOCKET=' /etc/default/opendkim; then
    sed -i 's|^SOCKET=.*|SOCKET=inet:8891@localhost|' /etc/default/opendkim
  else
    echo 'SOCKET=inet:8891@localhost' >> /etc/default/opendkim
  fi
else
  echo 'SOCKET=inet:8891@localhost' > /etc/default/opendkim
fi

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
systemctl restart opendkim
sleep 1
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
