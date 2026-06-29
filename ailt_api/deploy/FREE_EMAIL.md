# Free email for OTP (Ubuntu 26.04)

**Cost: $0** — uses your Gmail account via Google App Password.

**Trade-off:** emails show **From: your@gmail.com** (not `noreply@cheradip.com`). Fine for verification codes.

**Limit:** ~500 emails/day on free Gmail.

---

## Step 1 — Google App Password (browser)

1. https://myaccount.google.com/security → turn on **2-Step Verification**
2. https://myaccount.google.com/apppasswords
3. App: **Mail**, name: `AILT Server` → **Create**
4. Copy the **16-character** password (remove spaces when pasting)

---

## Step 2 — Server

```bash
cd /home/sasha/apps/cheradip/bcheradip
git pull
cd ailt_api
chmod +x scripts/setup-gmail-env.sh scripts/test_smtp.sh
bash scripts/setup-gmail-env.sh
```

Or edit `.env` manually:

```env
SMTP_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=sashafik.me@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM=AI Language Tutor <sashafik.me@gmail.com>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

Remove any `SMTP_HOST=127.0.0.1` lines.

---

## Step 3 — Test

```bash
sudo systemctl restart cheradip-ailt
./scripts/test_smtp.sh sashafik.me@gmail.com
```

---

## Later: noreply@cheradip.com

| Option | Cost |
|--------|------|
| Google Workspace | Paid |
| Amazon SES | ~$0.10 / 1,000 emails |
| cPanel hosting | ~$3–10/month |

See [SMTP_GMAIL.md](./SMTP_GMAIL.md) for troubleshooting.
