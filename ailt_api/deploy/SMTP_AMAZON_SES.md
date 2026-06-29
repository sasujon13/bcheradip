# Send from noreply@cheradip.com via Amazon SES

**Ubuntu 26.04:** use **direct SES in `.env`** — [SES_UBUNTU26.md](./SES_UBUNTU26.md) (recommended).

```
ailt_api  →  email-smtp.REGION.amazonaws.com:587  →  Gmail / Yahoo
            From: noreply@cheradip.com
```

Optional: Postfix relay (only if you need local mail too):

```
ailt_api  →  127.0.0.1:587  →  Postfix  →  Amazon SES  →  internet
```

---

## Part 1 — AWS SES setup (~15 min)

### 1.1 Create / open AWS account

Go to [AWS Console](https://console.aws.amazon.com/) → search **Amazon SES**.

Pick a **region** close to you (e.g. **Europe (Ireland) `eu-west-1`**). All SES settings and SMTP endpoint use that region.

### 1.2 Verify domain `cheradip.com`

SES → **Verified identities** → **Create identity** → **Domain** → `cheradip.com`.

SES shows DNS records to add. At your DNS provider add **all** of them:

| SES gives you | You add |
|---------------|---------|
| 3× **CNAME** (DKIM) | Name + value exactly as shown |
| 1× **TXT** (verification) | `_amazonses.cheradip.com` |

Wait until SES shows identity status **Verified** (5–30 min).

### 1.3 SPF (merge with existing or replace)

Add or update **TXT** on `@`:

```text
v=spf1 include:amazonses.com ~all
```

If you also send directly from the VPS IP later:

```text
v=spf1 include:amazonses.com ip4:163.227.144.146 ~all
```

### 1.4 Optional but recommended

| Type | Name | Value |
|------|------|-------|
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@cheradip.com` |
| A | `mail` | `163.227.144.146` (for bounces / consistency) |

### 1.5 Exit the SES sandbox

New SES accounts are in **sandbox** — you can only send **to verified addresses**.

SES → **Account dashboard** → **Request production access**.

Fill the form (use case: transactional OTP for mobile app). Approval often takes **24 hours** (sometimes same day).

Until approved, verify your test Gmail in SES (**Create identity** → **Email address**) to test.

### 1.6 Create SMTP credentials

SES → **SMTP settings** → **Create SMTP credentials**.

Save:

- **SMTP username** (looks like `AKIA...`)
- **SMTP password** (long string — shown once)

Note your **SMTP endpoint**, e.g.:

```text
email-smtp.eu-west-1.amazonaws.com
```

---

## Part 2 — Configure ailt_api (recommended on Ubuntu 26)

See **[SES_UBUNTU26.md](./SES_UBUNTU26.md)** or run:

```bash
cd ailt_api
bash scripts/setup-ses-env.sh
sudo systemctl restart cheradip-ailt
./scripts/test_smtp.sh your@gmail.com
```

`.env` example:

```env
SMTP_HOST=email-smtp.eu-west-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=AKIAxxxxxxxx
SMTP_PASSWORD=your-ses-smtp-password
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
```

---

## Part 2b — Optional: Postfix relay on the server

### Option A — interactive script

```bash
cd /home/sasha/apps/cheradip/bcheradip
git pull
cd ailt_api
sudo bash deploy/scripts/setup-postfix-ses-relay.sh
```

You will enter:

- SES region (e.g. `eu-west-1`)
- SMTP username
- SMTP password

### Option B — manual

Replace `eu-west-1` and credentials:

```bash
REGION=eu-west-1
SES_USER="AKIAxxxxxxxxxxxxxxxx"
SES_PASS="your-ses-smtp-password"

sudo postconf -e "relayhost = [email-smtp.${REGION}.amazonaws.com]:587"
sudo postconf -e "smtp_sasl_auth_enable = yes"
sudo postconf -e "smtp_sasl_security_options = noanonymous"
sudo postconf -e "smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd"
sudo postconf -e "smtp_tls_security_level = encrypt"
sudo postconf -e "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt"
sudo postconf -e "inet_protocols = ipv4"

sudo bash -c "cat > /etc/postfix/sasl_passwd <<EOF
[email-smtp.${REGION}.amazonaws.com]:587 ${SES_USER}:${SES_PASS}
EOF"
sudo chmod 600 /etc/postfix/sasl_passwd
sudo postmap /etc/postfix/sasl_passwd

# Disable OpenDKIM milter (SES signs mail — avoids double/conflicting DKIM)
sudo postconf -e "smtpd_milters ="
sudo postconf -e "non_smtpd_milters ="
sudo postconf -P "submission/inet/smtpd_milters="
sudo postconf -P "submission/inet/non_smtpd_milters="
sudo postconf -P "smtp/inet/smtpd_milters="
sudo postconf -P "smtp/inet/non_smtpd_milters="

sudo systemctl restart postfix
```

---

## Part 3 — ailt_api `.env` (Postfix relay path only)

If you use Postfix relay below, keep localhost SMTP:

```env
SMTP_HOST=127.0.0.1
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
```

If you use **direct SES** (recommended), skip Part 2b and use Part 2 instead.

---

## Part 4 — Test

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
./scripts/test_smtp.sh sashafik.me@gmail.com
sudo tail -20 /var/log/mail.log
```

**Success:** `status=sent` and relay shows `email-smtp.*.amazonaws.com`, not `gmail-smtp-in.l.google.com` directly from your VPS IP.

**Sandbox:** If Gmail is not verified in SES, you get a rejection until production access or you verify that email in SES.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `554 Message rejected: Email address is not verified` | SES sandbox — request production access or verify recipient |
| `535 Authentication Credentials Invalid` | Wrong SES SMTP user/pass or wrong region in relayhost |
| `550 5.7.1` from Gmail after SES relay | Wait for SES domain **Verified**; check SPF includes `amazonses.com` |
| Still direct to Gmail in logs | `postconf relayhost` empty — re-run setup script |
| OpenDKIM errors | Disabled when using SES — OK |

Check relay config:

```bash
postconf relayhost smtp_sasl_auth_enable
sudo postmap -q "[email-smtp.eu-west-1.amazonaws.com]:587" /etc/postfix/sasl_passwd
```

---

## Costs

Amazon SES: about **$0.10 per 1,000 emails** — negligible for OTP volume.

---

## Regions (SMTP endpoints)

| Region | SMTP endpoint |
|--------|----------------|
| eu-west-1 (Ireland) | `email-smtp.eu-west-1.amazonaws.com` |
| us-east-1 (N. Virginia) | `email-smtp.us-east-1.amazonaws.com` |
| ap-south-1 (Mumbai) | `email-smtp.ap-south-1.amazonaws.com` |

Use the region where you verified `cheradip.com` in SES.
