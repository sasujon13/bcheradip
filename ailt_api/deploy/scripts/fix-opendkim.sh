#!/usr/bin/env bash
# Fix OpenDKIM on Ubuntu/Debian + wire Postfix milter
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run: sudo bash $0"; exit 1; fi

DOMAIN=cheradip.com
SELECTOR=mail
KEY_DIR="/etc/opendkim/keys/${DOMAIN}"
PUBLIC_IP="${PUBLIC_IP:-163.227.144.146}"

echo "=== Install OpenDKIM ==="
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
chmod 600 "${KEY_DIR}/${SELECTOR}.private"

echo "=== KeyTable / SigningTable / TrustedHosts ==="
cat > /etc/opendkim/KeyTable <<EOF
${SELECTOR}._domainkey.${DOMAIN} ${DOMAIN}:${SELECTOR}:${KEY_DIR}/${SELECTOR}.private
EOF

cat > /etc/opendkim/SigningTable <<EOF
*@${DOMAIN} ${SELECTOR}._domainkey.${DOMAIN}
EOF

cat > /etc/opendkim/TrustedHosts <<EOF
127.0.0.1
localhost
::1
${PUBLIC_IP}
EOF

echo "=== opendkim.conf ==="
cat > /etc/opendkim.conf <<EOF
Syslog                  yes
LogWhy                  yes
UMask                   002
UserID                  opendkim
Mode                    sv
Canonicalization        relaxed/simple
SubDomains              no
AutoRestart             yes
AutoRestartRate         10/1M
Background              no
DNSTimeout              5
SignatureAlgorithm      rsa-sha256
OversignHeaders         From
KeyTable                refile:/etc/opendkim/KeyTable
SigningTable            refile:/etc/opendkim/SigningTable
ExternalIgnoreList      refile:/etc/opendkim/TrustedHosts
InternalHosts           refile:/etc/opendkim/TrustedHosts
EOF

echo "=== /etc/default/opendkim ==="
cat > /etc/default/opendkim <<'EOF'
SOCKET=inet:8891@localhost
PIDFILE=/run/opendkim/opendkim.pid
EOF
mkdir -p /run/opendkim
chown opendkim:opendkim /run/opendkim

echo "=== Postfix (IPv4 + milter) ==="
postconf -e 'inet_protocols = ipv4'
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
if ! systemctl restart opendkim; then
  echo ""
  echo "OpenDKIM failed — log:"
  journalctl -u opendkim -n 30 --no-pager || true
  echo ""
  echo "Try manual start:"
  echo "  sudo -u opendkim opendkim -f -x inet:8891@localhost -P /run/opendkim/opendkim.pid"
  exit 1
fi
sleep 2
systemctl restart postfix

echo ""
echo "=== Status ==="
systemctl is-active opendkim postfix
ss -tlnp | grep 8891 || echo "WARN: not listening on 8891"

echo ""
echo "=== DNS still required ==="
echo "  A     mail  -> ${PUBLIC_IP}   (MISSING if dig +short mail.${DOMAIN} A is empty)"
echo "  MX    @     -> 10 mail.${DOMAIN}"
echo "  TXT   @     -> v=spf1 ip4:${PUBLIC_IP} a mx ~all"
echo "  TXT   mail._domainkey -> (below)"
echo ""
cat "${KEY_DIR}/${SELECTOR}.txt"
echo ""
echo "PTR at VPS host: ${PUBLIC_IP} -> mail.${DOMAIN}"
