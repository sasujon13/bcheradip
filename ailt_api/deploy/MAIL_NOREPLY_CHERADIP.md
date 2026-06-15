# Send from noreply@cheradip.com (Gmail, Yahoo, others)

Goal: OTP and system mail **From `noreply@cheradip.com`**, SMTP login user **`admin`**, delivered to Gmail, Yahoo, Outlook, etc.

**Do not use** `127.0.0.1:25` without auth — Gmail returns `550 5.7.1`. Use **Postfix submission on 587** + DNS + DKIM.

```
ailt_api  --TLS+admin-->  127.0.0.1:587  --Postfix+OpenDKIM-->  Gmail / Yahoo / ...
         From: noreply@cheradip.com
```

---

## Step 1 — DNS (cheradip.com)

Replace `163.227.144.146` with your VPS public IP (`curl -4 ifconfig.me`).

| Type | Name | Value | Notes |
|------|------|-------|--------|
| **A** | `mail` | `163.227.144.146` | **DNS only** on Cloudflare (grey cloud) |
| **MX** | `@` | `10 mail.cheradip.com` | |
| **TXT** | `@` | `v=spf1 ip4:163.227.144.146 a mx ~all` | SPF |
| **TXT** | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@cheradip.com` | |
| **TXT** | `mail._domainkey` | *(from Step 3 — OpenDKIM)* | DKIM |

Verify (wait 5–30 min after saving):

```bash
dig +short mail.cheradip.com A
dig +short cheradip.com MX
dig +short mail._domainkey.cheradip.com TXT
```

**PTR (reverse DNS):** In your VPS panel, set reverse DNS for `163.227.144.146` → `mail.cheradip.com`. Gmail/Yahoo often reject without this.

---

## Step 2 — Install / fix Postfix + OpenDKIM on the server

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
git pull

# First time:
sudo bash deploy/scripts/install-mail-ubuntu.sh

# Already have Postfix but 587 / DKIM broken:
sudo bash deploy/scripts/fix-postfix-587.sh
sudo bash deploy/scripts/fix-opendkim.sh
```

The install script creates SASL user **`admin`** (password → `SMTP_PASSWORD` in `.env`).

Check services:

```bash
sudo systemctl status postfix opendkim --no-pager
ss -tlnp | grep -E ':587 |:8891 '
sudo sasldblistusers2
# expect: admin@mail.cheradip.com
```

Add or reset `admin` password anytime:

```bash
sudo bash deploy/scripts/setup-smtp-admin-user.sh
```

---

## Step 3 — Add DKIM TXT to DNS

After `fix-opendkim.sh` or install:

```bash
sudo cat /etc/opendkim/keys/cheradip.com/mail.txt
```

Copy the `p=...` public key into DNS **TXT** `mail._domainkey` (one line, no quotes in the middle).

---

## Step 4 — ailt_api `.env`

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

```env
SMTP_ENABLED=true
SMTP_HOST=127.0.0.1
SMTP_PORT=587
SMTP_USER=admin
SMTP_PASSWORD=your-saslpasswd2-password
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

- `SMTP_USER` is **`admin`** (short name), not `admin@cheradip.com`.
- `SMTP_FROM` is what recipients see — **`noreply@cheradip.com`**.
- `SMTP_USE_TLS=true` is **required** on port 587.
- `SMTP_HOST=127.0.0.1` is correct; the app skips TLS cert verify for localhost (Postfix cert is for `mail.cheradip.com`).
- `DEV_LOG_OTP=false` in production — if `true`, failed SMTP is hidden and OTP only prints to the console.

---

## Step 5 — Test delivery

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
./scripts/diagnose_smtp.sh
./scripts/test_smtp.sh sashafik.me@gmail.com
sudo systemctl restart cheradip-ailt
```

Watch logs while testing:

```bash
sudo tail -f /var/log/mail.log
```

Success: `status=sent` and mail in inbox (check spam once).

---

## Step 6 — Deliverability score

Send a test to [mail-tester.com](https://www.mail-tester.com) (address they give you):

```bash
./scripts/test_smtp.sh test-xxxxx@mail-tester.com
```

Aim for **8/10+**. Fix SPF, DKIM, DMARC, PTR if score is low.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Connection refused` on 587 | `sudo bash deploy/scripts/fix-postfix-587.sh` |
| `Authentication failed` | `sudo bash deploy/scripts/setup-smtp-admin-user.sh`; use user `admin` |
| OpenDKIM failed | `sudo bash deploy/scripts/fix-opendkim.sh` |
| `550 5.7.1 not authorized to send directly` | Complete DNS + DKIM + PTR; **never** use port 25 in `.env` |
| Mail in spam only | mail-tester.com; tighten DMARC to `p=quarantine` later |
| Still blocked by Gmail after DNS OK | New VPS IP — wait 24–48h, or ask host to fix PTR; see [SMTP_RELAY.md](./SMTP_RELAY.md) optional relays |

---

## Quick reference

| Setting | Value |
|---------|--------|
| From (visible) | `noreply@cheradip.com` |
| SMTP auth user | `admin` |
| SMTP host (app) | `127.0.0.1` |
| SMTP port | `587` + TLS |
| Mail hostname | `mail.cheradip.com` |

Fallback if domain mail cannot reach Gmail yet: [SMTP_GMAIL.md](./SMTP_GMAIL.md) (From will be `@gmail.com` until domain mail works).
