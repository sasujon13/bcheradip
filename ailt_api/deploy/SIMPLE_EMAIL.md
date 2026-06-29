# Send verification emails — simple guide

**Goal:** App sends OTP codes **From: noreply@cheradip.com**.

**Your app is already built for this.** You only need an SMTP server that Gmail trusts.

---

## Why it feels hard

Gmail **blocks** most home/VPS servers when they send mail directly (error `550 5.7.1`).  
That is normal. It is **not** a bug in your app.

**Fix:** Use a mail service that Gmail already trusts.

| Option | Cost | From address |
|--------|------|----------------|
| **Gmail SMTP** (recommended free) | **$0** | `your@gmail.com` |
| Amazon SES | ~$0.10 / 1,000 | `noreply@cheradip.com` |
| cPanel hosting | ~$3–10/mo | `noreply@cheradip.com` |

**Free setup:** [FREE_EMAIL.md](FREE_EMAIL.md) — Gmail App Password, no Postfix, no AWS.

---

## Paid / custom From — Amazon SES (optional)

### Step 1 — AWS (in your browser)

1. Open https://console.aws.amazon.com/ses/
2. Choose a region (example: **Europe Ireland / eu-west-1**).
3. **Verified identities** → **Create identity** → **Domain** → type `cheradip.com`.
4. AWS shows DNS records. Add **all of them** where you manage cheradip.com DNS (Cloudflare, Namecheap, etc.).
5. Add this **TXT** record on `@` (root domain) for SPF:
   ```
   v=spf1 include:amazonses.com ~all
   ```
6. Wait until AWS shows the domain as **Verified** (5–30 minutes).
7. Click **Request production access** (otherwise you can only send to addresses you verify in AWS). Approval often takes ~1 day.
8. Go to **SMTP settings** → **Create SMTP credentials**. Save:
   - SMTP username (starts with `AKIA…`)
   - SMTP password (long string — copy now)

Write down your SMTP host for that region, for example:
```
email-smtp.eu-west-1.amazonaws.com
```

### Step 2 — Server (one file to edit)

SSH to your server and edit:

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

**Replace the whole SMTP section** with (use your real values):

```env
SMTP_ENABLED=true
SMTP_HOST=email-smtp.eu-west-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=AKIAxxxxxxxxxxxxxxxx
SMTP_PASSWORD=your-ses-smtp-password-here
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

Save: `Ctrl+O`, Enter, `Ctrl+X`.

### Step 3 — Restart and test

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
sudo systemctl restart cheradip-ailt
./scripts/test_smtp.sh sashafik.me@gmail.com
```

Check your Gmail inbox (and spam once).

**Done.** No Postfix setup required.

---

## Alternative — cPanel (recommended if you use cPanel hosting)

**→ [CPANEL_EMAIL.md](CPANEL_EMAIL.md)** — full steps.

1. cPanel → **Email Accounts** → create `noreply@cheradip.com`
2. Put SMTP settings in `.env` on your Linux app server:

```env
SMTP_ENABLED=true
SMTP_HOST=mail.cheradip.com
SMTP_PORT=587
SMTP_USER=noreply@cheradip.com
SMTP_PASSWORD=password-from-cpanel
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

3. Restart and test (same as Step 3 above).

**Note:** Your app server is Ubuntu 26. Installing cPanel on it is **not recommended** — cPanel needs a specific OS (usually AlmaLinux) and a paid license, and it can conflict with your existing site setup.

---

## What you can ignore

| You can skip | Why |
|--------------|-----|
| Postfix on 127.0.0.1 | App talks to SES or cPanel directly |
| OpenDKIM on VPS | SES/cPanel handle signing |
| `setup-smtp-admin-user.sh` | Not needed for SES/cPanel |
| Port 25 | Not needed |

---

## If test fails

| Error | What to do |
|-------|------------|
| `Email address is not verified` | SES sandbox — wait for production access, or verify your Gmail in SES temporarily |
| `Authentication failed` | Wrong SMTP user/password or wrong region in `SMTP_HOST` |
| `535` with cPanel | Use full email as `SMTP_USER`; check password in cPanel |
| No error but no mail | Check spam; set `DEV_LOG_OTP=true` briefly to see codes in logs |

---

## Summary

1. **Easiest on your own VPS:** Amazon SES + `.env` (no extra software on the server).
2. **If you know cPanel:** use mail account on cPanel host, not on the app VPS.
3. **Do not** try to send straight from the VPS IP to Gmail — Google will keep blocking it.

Need help with one step? Say which: **AWS SES**, **DNS**, or **cPanel**.
