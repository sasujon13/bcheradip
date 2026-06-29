# Email — Brevo SMTP (OTP / verification)

All production mail goes through **Brevo** (`smtp-relay.brevo.com`).

---

## Email template

Edit the HTML file directly:

```
ailt_api/deploy/email-preview-otp.html
```

Placeholders (filled when sending):

| Placeholder | Example |
|-------------|---------|
| `{{purpose}}` | Password reset |
| `{{code}}` | 482916 |
| `{{code_digits}}` | styled digit spans (auto) |
| `{{ttl_minutes}}` | 15 |

After editing, restart the API and send a test:

```bash
sudo systemctl restart cheradip-ailt
cd ailt_api && bash scripts/test_smtp.sh your@gmail.com
```

Health check:

```bash
curl -s http://127.0.0.1:8790/api/ailt/health | python3 -m json.tool
# "email_template": "otp-email-preview"
# "email_template_ok": true
```

---

## Production `.env`

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

---

## Deploy template to server

```bash
cd /home/sasha/apps/cheradip/bcheradip
git pull   # or: git checkout origin/main -- ailt_api/deploy/email-preview-otp.html ailt_api/app/services/
sudo systemctl restart cheradip-ailt
bash ailt_api/scripts/test_smtp.sh your@gmail.com
```

If `git pull` fails (divergent branches):

```bash
git fetch origin
git checkout origin/main -- \
  ailt_api/deploy/email-preview-otp.html \
  ailt_api/app/services/email_templates.py \
  ailt_api/app/services/email_service.py \
  ailt_api/app/main.py
sudo systemctl restart cheradip-ailt
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `535 Authentication failed` | Use **SMTP key** as password |
| Plain text only, no HTML | Server running old code — checkout files above |
| `email_template_ok: false` | Missing `deploy/email-preview-otp.html` on server |
| Logo missing in Gmail | Inline SVG may be stripped by Gmail — edit template to use PNG `<img>` if needed |

Logs: `journalctl -u cheradip-ailt -f`
