# Send OTP verification codes via Gmail SMTP

Gmail **rejects** mail sent directly from your VPS (`127.0.0.1:25` / Postfix → `550 5.7.1`).

**Use Gmail’s SMTP server** from `ailt_api` — no Brevo, no local Postfix for delivery.

---

## Step 1 — Google App Password

1. Open https://myaccount.google.com/security  
2. Turn on **2-Step Verification** (required).  
3. **App passwords** → app: **Mail**, device: **Other** → name: `Cheradip AILT`.  
4. Copy the **16-character** password (e.g. `abcd efgh ijkl mnop`).

Use the Gmail account that should **send** OTP mail (e.g. `sashafik.me@gmail.com`).

---

## Step 2 — Server `.env`

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

**Replace the entire SMTP block** with:

```env
SMTP_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=sashafik.me@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM=AI Language Tutor <sashafik.me@gmail.com>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

Rules:

- `SMTP_PASSWORD` = **App password only** (not your normal Gmail password).  
- `SMTP_USER` and `SMTP_FROM` must match the same Gmail account (or use `SMTP_FROM=sashafik.me@gmail.com`).  
- **Do not use** `SMTP_HOST=127.0.0.1` or `SMTP_PORT=25`.

Remove any old lines:

```env
# DELETE these — they do not reach Gmail:
# SMTP_HOST=127.0.0.1
# SMTP_PORT=25
```

---

## Step 3 — Test

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
./scripts/test_smtp.sh sashafik.me@gmail.com
sudo systemctl restart cheradip-ailt
```

Expect: email with verification code **123456** in inbox (check spam once).

---

## Step 4 — App signup

Register in the Android app → OTP email should arrive within ~1 minute.

---

## Troubleshooting

| Error | Fix |
|--------|-----|
| `535 Username and Password not accepted` | Use **App password**, not normal password; 2FA must be on |
| `Local Postfix cannot deliver to Gmail` | You still have `127.0.0.1:25` in `.env` — switch to Gmail block above |
| Mail in spam | Normal first time; mark “Not spam” |
| `Connection refused` to smtp.gmail.com | Check firewall allows **outbound 587** |

Logs:

```bash
journalctl -u cheradip-ailt -f
```

---

## Limits

- Gmail free: about **500 emails/day** — fine for OTP / early users.  
- **From address** shows your `@gmail.com` (not `noreply@cheradip.com`) unless you later use **Google Workspace** on `cheradip.com`.

---

## Optional later: `noreply@cheradip.com`

Without Brevo, options are:

- **Google Workspace** on `cheradip.com` → same SMTP setup, custom From.  
- Or keep **`sashafik.me@gmail.com`** as sender for now (works for verification).

Postfix on the VPS can stay installed; **do not** point `ailt_api` at `127.0.0.1:25` for OTP.
