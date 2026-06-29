# Brevo SMTP — noreply@cheradip.com (free tier)

Send OTP as **`noreply@cheradip.com`** via Brevo. Works on **Ubuntu 26.04** — no Postfix.

---

## Step 1 — Verify domain in Brevo (required)

1. Brevo → **Senders, domains & dedicated IPs** → **Domains**
2. Add **`cheradip.com`**
3. Add **all DNS records** Brevo shows (SPF, DKIM) at Cloudflare/Namecheap
4. Wait until status = **Verified**

Without this, `From: noreply@cheradip.com` will fail or go to spam.

Optional: add sender **`noreply@cheradip.com`** under **Senders** after domain is verified.

---

## Step 2 — SMTP credentials (Brevo dashboard)

**SMTP & API** → **SMTP** → copy:

| Field | Use in `.env` |
|-------|----------------|
| **Server** | `SMTP_HOST` |
| **Port** | `587` → `SMTP_PORT` |
| **Login** | `SMTP_USER` (often `xxxx@smtp-brevo.com`) |
| **SMTP key** | `SMTP_PASSWORD` |

**Do not** put the **API key** (`xkeysib-...`) in `SMTP_PASSWORD` — that is for REST API, not SMTP.

If you signed up with **Google login**, `SMTP_USER` is still the **Login** from the SMTP page (not necessarily your Gmail).

---

## Step 3 — `ailt_api/.env`

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

```env
SMTP_ENABLED=true
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=a0ced8001@smtp-brevo.com
SMTP_PASSWORD=your-smtp-key-from-brevo-dashboard
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

Remove old lines (`SMTP_HOST=127.0.0.1`, Gmail, SES).

---

## Step 4 — Test

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
sudo systemctl restart cheradip-ailt
./scripts/test_smtp.sh sashafik.me@gmail.com
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `535 Authentication failed` | Use **SMTP key** as password, not API key; check Login matches dashboard |
| `Sender not valid` / rejected | Verify **cheradip.com** domain in Brevo |
| Mail in spam | Complete DKIM/SPF in DNS; mark “Not spam” once |

---

## Limits

Brevo free tier: about **300 emails/day** — enough for OTP during early growth.

---

## Security

- Never commit `.env` or API keys to git
- If keys were shared in chat, **rotate SMTP key** in Brevo dashboard
