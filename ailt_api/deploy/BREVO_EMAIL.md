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

## Test

```bash
sudo systemctl restart cheradip-ailt
bash scripts/test_smtp.sh sashafik.me@gmail.com
```

If you see `Permission denied`, use `bash scripts/test_smtp.sh ...` (Windows git may not preserve the executable bit).

The test script **always fails loudly** if SMTP does not connect (no silent success when `DEV_LOG_OTP=true`).

**Verify branded template is deployed:**

```bash
curl -s https://cheradip.com/ailt/api/health | python3 -m json.tool
# Must include: "email_template": "otp-html-v4"
```

If `email_template` is missing, the server is still running **old code**.

**If `git pull` fails with "divergent branches"** — `git fetch` alone does **not** update files. You must checkout from `origin/main`:

```bash
cd /home/sasha/apps/cheradip/bcheradip
git fetch origin
git checkout origin/main -- ailt_api/scripts/deploy-email.sh
bash ailt_api/scripts/deploy-email.sh
```

Or manually:

```bash
cd /home/sasha/apps/cheradip/bcheradip
git fetch origin
git checkout origin/main -- \
  ailt_api/app/services/email_templates.py \
  ailt_api/app/services/email_service.py \
  ailt_api/app/main.py \
  ailt_api/app/config.py \
  ailt_api/app/assets/email/ \
  ailt_api/scripts/
bash ailt_api/scripts/build-email-assets.sh
sudo systemctl restart cheradip-ailt
```

If health shows `Expecting value: line 1 column 1`, the API is not responding on port 8790:

```bash
sudo systemctl status cheradip-ailt
journalctl -u cheradip-ailt -n 40 --no-pager
curl -v http://127.0.0.1:8790/api/ailt/health
```

Or reset the whole repo to GitHub (drops server-only local commits):

```bash
cd /home/sasha/apps/cheradip/bcheradip
git fetch origin
git reset --hard origin/main
sudo systemctl restart cheradip-ailt
```

Confirm files exist:

```bash
grep otp-html-v4 ailt_api/app/services/email_templates.py
ls ailt_api/app/assets/email/cheradip-avatar.png ailt_api/app/assets/email/cheradip-wordmark.png
bash ailt_api/scripts/build-email-assets.sh   # if PNGs missing
curl -sI https://cheradip.com/ailt/api/assets/email/cheradip-avatar.png | head -1
```

In Gmail: open the email → **⋮ → Show original** → search for `otp-html-v4` and `cheradip-avatar.png`.

**Why not cid: inline images?** Brevo SMTP **strips Content-ID** on transactional mail — logos must use **HTTPS URLs**. The API serves PNGs at `/ailt/api/assets/email/`.

**Inbox circle logo (instead of “C”):** see [BIMI_INBOX_LOGO.md](BIMI_INBOX_LOGO.md).


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
