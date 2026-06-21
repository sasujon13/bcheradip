# Send email with cPanel — noreply@cheradip.com

Use cPanel for mail. Your **Linux app server** only needs `.env` settings — no Postfix, no SES.

---

## Before you start

You need **cPanel hosting** for `cheradip.com` (your web host account with cPanel).

- The **website** can stay on your VPS.
- **Email** lives on the cPanel server.
- **MX records** in DNS must point to the cPanel mail server (cPanel shows the values).

---

## Step 1 — Create the email in cPanel

1. Log in to **cPanel** (your hosting provider).
2. Open **Email Accounts**.
3. Click **Create**.
4. Fill in:
   - **Email:** `noreply`
   - **Domain:** `cheradip.com`
   - **Password:** choose a strong password (save it)
   - **Storage:** 250 MB is enough for OTP
5. Click **Create**.

You now have **noreply@cheradip.com**.

---

## Step 2 — Get SMTP settings from cPanel

In cPanel → **Email Accounts** → find `noreply@cheradip.com` → **Connect Devices** or **Configure Mail Client**.

Use these values (typical):

| Setting | Value |
|---------|--------|
| SMTP server | `mail.cheradip.com` (or what cPanel shows) |
| Port | **587** with TLS, or **465** with SSL |
| Username | `noreply@cheradip.com` (full email) |
| Password | the password you set in Step 1 |

If `mail.cheradip.com` does not work, use the **server hostname** cPanel shows (e.g. `server123.yourhost.com`).

---

## Step 3 — DNS (if not done already)

In cPanel → **Zone Editor** or your DNS provider:

| Type | Name | Value |
|------|------|-------|
| **MX** | `@` | cPanel mail server (priority 0 or 10 — cPanel shows this) |
| **A** | `mail` | IP of cPanel mail server (if cPanel asks for it) |

Wait 15–30 minutes after changes.

Check:

```bash
dig +short cheradip.com MX
```

---

## Step 4 — Edit `.env` on your Linux app server

SSH to your server:

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

**Replace the SMTP section** with (use your real password):

### Option A — port 587 + TLS (try this first)

```env
SMTP_ENABLED=true
SMTP_HOST=mail.cheradip.com
SMTP_PORT=587
SMTP_USER=noreply@cheradip.com
SMTP_PASSWORD=your-cpanel-email-password
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

### Option B — port 465 + SSL (if 587 fails)

```env
SMTP_ENABLED=true
SMTP_HOST=mail.cheradip.com
SMTP_PORT=465
SMTP_USER=noreply@cheradip.com
SMTP_PASSWORD=your-cpanel-email-password
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=false
SMTP_USE_SSL=true
DEV_LOG_OTP=false
```

Save: `Ctrl+O`, Enter, `Ctrl+X`.

**Important:** `SMTP_USER` must be the **full email** `noreply@cheradip.com`, not just `noreply`.

---

## Step 5 — Test

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
sudo systemctl restart cheradip-ailt
./scripts/test_smtp.sh sashafik.me@gmail.com
```

Check Gmail inbox and spam.

---

## If it fails

| Problem | Fix |
|---------|-----|
| `Authentication failed` | Wrong password; use full email as `SMTP_USER` |
| `Connection refused` / timeout | Wrong `SMTP_HOST` — copy exact host from cPanel |
| Try port 465 | Switch to Option B above |
| Mail not received | Check spam; verify MX points to cPanel |
| `Name or service not known` | Add **A** record for `mail.cheradip.com` in DNS |

---

## You do NOT need on the app VPS

- Postfix
- OpenDKIM
- Amazon SES
- Port 25

The app connects **directly to cPanel’s mail server**.

---

## Summary

1. cPanel → create **noreply@cheradip.com**
2. Copy SMTP host, port, password into **`.env`**
3. Restart app → test

Done.
