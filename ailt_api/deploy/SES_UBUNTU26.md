# Amazon SES on Ubuntu 26.04 — noreply@cheradip.com

**Works on Ubuntu 26.04.** No Postfix, no HestiaCP, no cPanel.

```
ailt_api  →  Amazon SES SMTP  →  Gmail / Yahoo / …
            From: noreply@cheradip.com
```

Cost: about **$0.10 per 1,000 emails**.

---

## Part A — AWS (browser, ~20 min)

### A1. Open SES

1. Go to https://console.aws.amazon.com/ses/
2. Top-right: pick a **region** (example: **Europe (Ireland) eu-west-1**).
3. Stay in that region for all steps below.

### A2. Verify domain

1. **Verified identities** → **Create identity**
2. **Identity type:** Domain  
3. **Domain:** `cheradip.com`
4. **Use default DKIM:** ON  
5. Create

AWS shows DNS records. In **Cloudflare / Namecheap** (where cheradip.com DNS lives), add **every record** AWS lists:

- Usually **3 CNAME** (DKIM)
- **1 TXT** for `_amazonses.cheradip.com`

Also add **SPF** (TXT on `@`):

```text
v=spf1 include:amazonses.com ~all
```

Optional **DMARC** (TXT on `_dmarc`):

```text
v=DMARC1; p=none; rua=mailto:admin@cheradip.com
```

Wait until SES shows **Verified** (5–30 min). Refresh the SES page.

### A3. Leave sandbox (required for any Gmail user)

New accounts are in **sandbox** (only verified recipients).

1. SES → **Account dashboard** → **Request production access**
2. Mail type: **Transactional**
3. Website: `https://cheradip.com`
4. Description example:
   > Mobile app AI Language Tutor sends email verification codes (OTP) to users who sign up. About 10–500 emails/day.

Submit. Approval often takes **a few hours to 1 day**.

**While waiting:** SES → **Create identity** → **Email address** → add `sashafik.me@gmail.com` to test.

### A4. SMTP credentials

1. SES → **SMTP settings** → **Create SMTP credentials**
2. Save **both** (password shown **once**):
   - Username: `AKIA...`
   - Password: long random string

3. Note **SMTP endpoint** for your region:

| Region | SMTP_HOST |
|--------|-----------|
| eu-west-1 (Ireland) | `email-smtp.eu-west-1.amazonaws.com` |
| us-east-1 (Virginia) | `email-smtp.us-east-1.amazonaws.com` |
| ap-south-1 (Mumbai) | `email-smtp.ap-south-1.amazonaws.com` |

---

## Part B — Ubuntu 26 server (SSH)

### B1. Pull latest + run setup script

```bash
cd /home/sasha/apps/cheradip/bcheradip
git pull
cd ailt_api
chmod +x scripts/setup-ses-env.sh scripts/test_smtp.sh
bash scripts/setup-ses-env.sh
```

The script asks for:

- SES region (e.g. `eu-west-1`)
- SMTP username (`AKIA...`)
- SMTP password

It writes `ailt_api/.env` SMTP settings.

### B2. Or edit `.env` manually

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

```env
SMTP_ENABLED=true
SMTP_HOST=email-smtp.eu-west-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=AKIAxxxxxxxxxxxxxxxx
SMTP_PASSWORD=your-ses-smtp-password
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

**Remove** old localhost lines:

```env
# DELETE these if still present:
# SMTP_HOST=127.0.0.1
# SMTP_PORT=587
# SMTP_USER=
```

### B3. Restart and test

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
sudo systemctl restart cheradip-ailt
./scripts/test_smtp.sh sashafik.me@gmail.com
```

Success: no error, email in inbox (check spam once).

---

## Part C — Android app

No app change needed if API URL is already `https://cheradip.com/ailt/api/`.  
OTP is sent by the server when users sign up / verify email.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `535 Authentication Credentials Invalid` | Wrong user/password, or `SMTP_HOST` region ≠ SES region |
| `554 Message rejected: Email address is not verified` | Still in sandbox — verify recipient email in SES or wait for production access |
| `Message rejected: Email address is not verified` (From) | Domain `cheradip.com` not **Verified** in SES — finish DNS |
| Connection timeout | Server firewall must allow **outbound 587** (`curl -v telnet://email-smtp.eu-west-1.amazonaws.com:587`) |
| Test OK, app still fails | Restart: `sudo systemctl restart cheradip-ailt` |

Check what the app loads:

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
grep '^SMTP_' .env | sed 's/PASSWORD=.*/PASSWORD=***/'
```

---

## You do NOT need on Ubuntu 26

- Postfix / OpenDKIM
- HestiaCP / cPanel
- Port 25
- `mail.cheradip.com` A record (optional; SES handles delivery)

---

## Checklist

- [ ] SES domain `cheradip.com` = **Verified**
- [ ] SPF `include:amazonses.com` in DNS
- [ ] **Production access** approved (or test Gmail verified in sandbox)
- [ ] SMTP credentials created
- [ ] `.env` updated on server
- [ ] `cheradip-ailt` restarted
- [ ] `./scripts/test_smtp.sh` succeeds

---

## Optional: Postfix relay instead of direct SES

Only if you want all server mail to go through SES. See [SMTP_AMAZON_SES.md](./SMTP_AMAZON_SES.md) (Postfix path).  
For Ubuntu 26, **direct SES in `.env` is simpler**.
