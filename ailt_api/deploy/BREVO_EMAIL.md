# Email — Brevo SMTP (OTP / verification)

All production mail goes through **Brevo** (`smtp-relay.brevo.com`). No Postfix, AWS SES, cPanel, or Gmail SMTP on the server.

---

## Verified senders (cheradip.com)

| Display | Address | Use for |
|---------|---------|---------|
| Cheradip | `noreply@cheradip.com` | **OTP / signup** (default) |
| Cheradip | `admin@cheradip.com` | Admin notifications |
| Cheradip | `support@cheradip.com` | Support mail |

Domain **cheradip.com** must stay **Verified** in Brevo (DKIM + DMARC configured).

---

## Production `.env`

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

```env
SMTP_ENABLED=true
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=your-login@smtp-brevo.com
SMTP_PASSWORD=your-brevo-smtp-key
SMTP_FROM=Cheradip <noreply@cheradip.com>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

| Field | Where to get it |
|-------|-----------------|
| `SMTP_USER` | Brevo → **SMTP & API** → SMTP → **Login** |
| `SMTP_PASSWORD` | Brevo → **SMTP key** (not the `xkeysib-` API key) |
| `SMTP_FROM` | Must match a **verified sender** in Brevo |

Other From addresses (same SMTP login):

```env
SMTP_FROM=Cheradip <admin@cheradip.com>
SMTP_FROM=Cheradip <support@cheradip.com>
```

---

## Setup script

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
git pull
chmod +x scripts/setup-brevo-env.sh scripts/test_smtp.sh
bash scripts/setup-brevo-env.sh
```

---

## Email template

OTP emails use a branded **HTML + plain-text** template (`app/services/email_templates.py`) with the Cheradip logo (`app/assets/email/cheradip.svg`) and app colors (teal `#00897B`, green gradient header).

After deploy, test:

```bash
./scripts/test_smtp.sh your@gmail.com
```


---

## Local development (Windows / XAMPP)

Use a local fake SMTP (MailHog, `server/mail/run-dev-smtp.ps1` in Android repo) — **not** Brevo:

```env
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=false
DEV_LOG_OTP=true
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `535 Authentication failed` | Use **SMTP key** as password; `SMTP_USER` = Login from Brevo SMTP page |
| Sender rejected | Sender must be verified in Brevo; check `SMTP_FROM` spelling |
| Mail in spam | Normal first time; mark “Not spam” |
| `SMTP_HOST=127.0.0.1` in production | Wrong — use `smtp-relay.brevo.com` |

Logs: `journalctl -u cheradip-ailt -f`

---

## Limits

Brevo free tier: about **300 emails/day** — sufficient for OTP during early growth.

---

## Security

- Never commit `.env` or API keys to git
- Rotate SMTP key in Brevo if exposed
