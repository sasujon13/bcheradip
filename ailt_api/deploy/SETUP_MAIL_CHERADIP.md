# Set up mail.cheradip.com on your Linux VPS

> **Quick path:** **[MAIL_NOREPLY_CHERADIP.md](./MAIL_NOREPLY_CHERADIP.md)** — `noreply@cheradip.com`, SMTP user `admin`, port 587. This file is the detailed reference.

Goal: send OTP email from **`noreply@cheradip.com`** for AILT (`ailt_api`) and optionally main Cheradip Django site.

**Stack:** Postfix (send) + OpenDKIM (signing) + DNS on **cheradip.com**

**Time:** ~30–60 minutes first time.

Replace `YOUR_SERVER_IP` with your VPS public IP (same IP as `cheradip.com` A record is fine).

---

## Overview

```
ailt_api  --SMTP-->  127.0.0.1:587  --Postfix-->  Internet
                              |
                         OpenDKIM signs mail
                              |
                    From: noreply@cheradip.com
```

You need:

1. DNS records (MX, A, SPF, DKIM, DMARC)
2. Postfix + OpenDKIM on the VPS
3. SMTP user/password for `ailt_api/.env`
4. Firewall open for **587** (submission)

---

## Step 0 — Before you start

On the server:

```bash
hostname -f
curl -4 ifconfig.me          # your public IPv4
dig +short cheradip.com A
getent hosts mail.cheradip.com
```

**Cloudflare users:** `mail.cheradip.com` must be **DNS only** (grey cloud ☁️), **not** proxied (orange). Mail cannot go through Cloudflare HTTP proxy.

**Port 25:** Some VPS providers block outbound port 25. Check:

```bash
nc -vz gmail-smtp-in.l.google.com 25
```

If it **times out**, you must use a **relay** (see [Appendix B](#appendix-b--port-25-blocked-relay-through-brevo) at the end) instead of direct send.

---

## Step 1 — DNS records

Add these at your DNS provider (Cloudflare, Namecheap, etc.) for **cheradip.com**:

| Type | Name | Content | Notes |
|------|------|---------|--------|
| **A** | `mail` | `YOUR_SERVER_IP` | DNS only if Cloudflare |
| **MX** | `@` | `mail.cheradip.com` | Priority **10** |
| **TXT** | `@` | `v=spf1 ip4:YOUR_SERVER_IP a mx ~all` | SPF |
| **TXT** | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@cheradip.com` | Start with p=none |
| **TXT** | `mail._domainkey` | *(from Step 4 after OpenDKIM)* | DKIM |

Wait 5–30 minutes, then verify:

```bash
dig +short mail.cheradip.com A
dig +short cheradip.com MX
dig +short cheradip.com TXT
```

---

## Step 2 — Install Postfix + OpenDKIM (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y postfix opendkim opendkim-tools mailutils libsasl2-modules sasl2-bin

# During postfix install prompts:
# - Internet Site
# - System mail name: cheradip.com
```

Create mail user for app SMTP auth:

```bash
# Password for ailt_api .env — pick a strong random password
sudo saslpasswd2 -c -u mail.cheradip.com admin
# Enter password twice — REMEMBER IT → SMTP_PASSWORD in .env (SMTP_USER=admin)
sudo chown postfix:postfix /etc/sasldb2
sudo chmod 660 /etc/sasldb2
```

Verify SASL user:

```bash
sudo sasldblistusers2
# should show: admin@mail.cheradip.com
```

---

## Step 3 — Postfix configuration

```bash
sudo postconf -e 'myhostname = mail.cheradip.com'
sudo postconf -e 'mydomain = cheradip.com'
sudo postconf -e 'myorigin = $mydomain'
sudo postconf -e 'inet_interfaces = loopback-only'
sudo postconf -e 'mydestination = $myhostname, localhost.$mydomain, localhost'
sudo postconf -e 'smtpd_banner = $myhostname ESMTP'
sudo postconf -e 'smtpd_tls_cert_file = /etc/ssl/certs/ssl-cert-snakeoil.pem'
sudo postconf -e 'smtpd_tls_key_file = /etc/ssl/private/ssl-cert-snakeoil.key'
sudo postconf -e 'smtpd_tls_security_level = may'
sudo postconf -e 'smtp_tls_security_level = may'

# Submission on 587 (localhost + apps on same server)
sudo postconf -M submission/inet="submission inet n       -       y       -       -       smtpd"
sudo postconf -P "submission/inet/syslog_name=postfix/submission"
sudo postconf -P "submission/inet/smtpd_tls_security_level=encrypt"
sudo postconf -P "submission/inet/smtpd_sasl_auth_enable=yes"
sudo postconf -P "submission/inet/smtpd_sasl_type=dovecot"
sudo postconf -P "submission/inet/smtpd_sasl_path=private/auth"
sudo postconf -P "submission/inet/smtpd_recipient_restrictions=permit_sasl_authenticated,reject"
sudo postconf -P "submission/inet/smtpd_sasl_local_domain=mail.cheradip.com"
sudo postconf -P "submission/inet/milter_protocol=6"
sudo postconf -P "submission/inet/milter_default_action=accept"
sudo postconf -P "submission/inet/smtpd_milters=inet:localhost:8891"
sudo postconf -P "submission/inet/non_smtpd_milters=inet:localhost:8891"
```

**Simpler SASL (without Dovecot)** — if submission SASL fails, use this instead:

```bash
sudo apt install -y libsasl2-modules
sudo postconf -P "submission/inet/smtpd_sasl_auth_enable=yes"
sudo postconf -P "submission/inet/smtpd_sasl_security_options=noanonymous"
sudo postconf -P "submission/inet/broken_sasl_auth_clients=yes"
sudo postconf -P "submission/inet/smtpd_sasl_type=cyrus"
sudo postconf -P "submission/inet/smtpd_sasl_path=sasldb"
sudo postconf -P "submission/inet/cyrus_sasl_config_path=/etc/sasl2"
```

Create `/etc/postfix/sasl/smtpd.conf`:

```
pwcheck_method: auxprop
auxprop_plugin: sasldb
mech_list: PLAIN LOGIN
```

```bash
sudo mkdir -p /etc/postfix/sasl
sudo nano /etc/postfix/sasl/smtpd.conf   # paste above
sudo systemctl restart postfix
```

**Allow noreply@cheradip.com as sender:**

```bash
sudo nano /etc/postfix/generic
```

Add:

```
admin@mail.cheradip.com noreply@cheradip.com
noreply@mail.cheradip.com noreply@cheradip.com
@mail.cheradip.com @cheradip.com
```

```bash
sudo postconf -e 'smtp_generic_maps = hash:/etc/postfix/generic'
sudo postmap /etc/postfix/generic
```

---

## Step 4 — OpenDKIM

```bash
sudo mkdir -p /etc/opendkim/keys/cheradip.com
sudo opendkim-genkey -b 2048 -d cheradip.com -D /etc/opendkim/keys/cheradip.com -s mail -v
sudo chown -R opendkim:opendkim /etc/opendkim
```

Show DKIM public key for DNS:

```bash
sudo cat /etc/opendkim/keys/cheradip.com/mail.txt
```

Copy the `p=...` value into DNS:

| Type | Name | Content |
|------|------|---------|
| TXT | `mail._domainkey` | `v=DKIM1; k=rsa; p=YOUR_PUBLIC_KEY` |

Configure OpenDKIM:

```bash
sudo nano /etc/opendkim.conf
```

Ensure these lines exist (adjust if file differs):

```
Syslog                  yes
UMask                   007
Canonicalization        relaxed/simple
Mode                    sv
SubDomains              no
AutoRestart             yes
AutoRestartRate         10/1M
Background              yes
DNSTimeout              5
SignatureAlgorithm      rsa-sha256

Domain                  cheradip.com
KeyFile                 /etc/opendkim/keys/cheradip.com/mail.private
Selector                mail

Socket                  inet:8891@localhost
```

```bash
sudo nano /etc/default/opendkim
```

Set:

```
SOCKET=inet:8891@localhost
```

```bash
sudo systemctl enable opendkim
sudo systemctl restart opendkim
sudo systemctl restart postfix
```

---

## Step 5 — Firewall

```bash
sudo ufw allow 587/tcp
sudo ufw allow 25/tcp    # optional inbound; outbound often still needed
sudo ufw status
```

---

## Step 6 — Test Postfix (before ailt_api)

```bash
# Install swaks if helpful
sudo apt install -y swaks

# Test authenticated submission
swaks --to sashafik.me@gmail.com \
  --from noreply@cheradip.com \
  --server 127.0.0.1:587 \
  --auth LOGIN \
  --auth-user admin \
  --auth-password 'YOUR_SASL_PASSWORD' \
  --tls
```

Or simple local test:

```bash
echo "Test body" | mail -s "Cheradip mail test" -r noreply@cheradip.com sashafik.me@gmail.com
```

Check logs:

```bash
sudo tail -f /var/log/mail.log
```

---

## Step 7 — ailt_api `.env`

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

```env
SMTP_ENABLED=true
SMTP_HOST=127.0.0.1
SMTP_PORT=587
SMTP_FROM=noreply@cheradip.com
SMTP_USER=admin
SMTP_PASSWORD=THE_PASSWORD_YOU_SET_WITH_saslpasswd2
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

**Where `SMTP_PASSWORD` comes from:** the password you typed when running:

```bash
sudo saslpasswd2 -c -u mail.cheradip.com admin
```

That is **your** password — you create it; nothing is auto-generated except you pick it.

Test:

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
./scripts/test_smtp.sh sashafik.me@gmail.com
sudo systemctl restart cheradip-ailt
```

---

## Step 8 — TLS certificate (recommended)

For production, use Let's Encrypt for `mail.cheradip.com`:

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d mail.cheradip.com
```

Then point Postfix to:

```
smtpd_tls_cert_file = /etc/letsencrypt/live/mail.cheradip.com/fullchain.pem
smtpd_tls_key_file = /etc/letsencrypt/live/mail.cheradip.com/privkey.pem
```

```bash
sudo systemctl restart postfix
```

---

## Troubleshooting

| Problem | What to do |
|---------|------------|
| `Name or service not known` for mail.cheradip.com | Add **A** record; wait for DNS; use `127.0.0.1` in `.env` until DNS works |
| `Authentication failed` | Re-run `setup-smtp-admin-user.sh`; user is **`admin`** not full email |
| Mail in spam | Complete SPF + DKIM + DMARC; use [mail-tester.com](https://www.mail-tester.com) |
| Connection refused on 587 | `sudo systemctl status postfix`; check `ss -tlnp \| grep 587` |
| Queue stuck | `mailq` then `sudo postqueue -f` |

---

## Appendix A — Do not use `127.0.0.1:25` for Gmail OTP

Postfix on port 25 accepts mail locally but **Gmail rejects** direct VPS delivery (`550 5.7.1`). OTP will not arrive.

Use **[SMTP_GMAIL.md](./SMTP_GMAIL.md)** for production OTP.

---

## Appendix B — Gmail SMTP (works when Postfix does not)

If self-hosted Postfix cannot reach Gmail inboxes, send from `ailt_api` via Gmail:

See **[SMTP_GMAIL.md](./SMTP_GMAIL.md)** — App Password, `.env`, test script.

---

## Appendix C — Django Cheradip site (optional)

In main `bcheradip/.env` for existing verification emails:

```env
EMAIL_HOST=127.0.0.1
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=admin
EMAIL_HOST_PASSWORD=same_as_ailt_api
DEFAULT_FROM_EMAIL=Cheradip <noreply@cheradip.com>
```

Add to `backend/settings.py` if not present:

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='127.0.0.1')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@cheradip.com')
```
