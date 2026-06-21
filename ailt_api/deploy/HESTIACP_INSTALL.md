# HestiaCP — free install guide (cheradip.com)

**Yes — HestiaCP is 100% free and open source.** No license fee (unlike cPanel).

- Website: https://hestiacp.com  
- Panel URL after install: **`https://YOUR_IP:8083`** (port **8083**, not 2083)

---

## Before you install — read this

| Topic | Detail |
|-------|--------|
| **Supported OS** | Ubuntu **20.04 / 22.04 / 24.04**, Debian 11/12 |
| **Your OS** | If you run **Ubuntu 26**, the installer **will refuse** — use **Ubuntu 24.04 LTS** or wait for HestiaCP support |
| **Fresh server** | HestiaCP wants a **clean** system. You already run nginx, MySQL, Django, ailt_api — **back up first**; conflicts are likely |
| **Home PC** | Forward router ports **8083**, **80**, **443**, **25**, **587** to your PC |
| **RAM** | Minimum 1 GB; **2 GB+** recommended |

---

## Part 1 — Backup (required on existing server)

```bash
# MySQL dump
mysqldump -u cheradip_cheradip -p ailanguagetutor > ~/backup-ailanguagetutor.sql
mysqldump -u cheradip_cheradip -p cheradip > ~/backup-cheradip.sql 2>/dev/null || true

# App files
tar -czf ~/backup-bcheradip.tar.gz -C /home/sasha/apps/cheradip bcheradip

# nginx + systemd
sudo tar -czf ~/backup-nginx-systemd.tar.gz /etc/nginx/sites-enabled /etc/systemd/system/cheradip*.service 2>/dev/null || true

# env (secrets)
cp /home/sasha/apps/cheradip/bcheradip/ailt_api/.env ~/backup-ailt_api.env
```

Copy backups to another disk or PC.

---

## Part 2 — Prepare the server

SSH as **root** (or use `sudo -i`).

### 2.1 Check Ubuntu version

```bash
lsb_release -rs
```

Must show **22.04** or **24.04** for official support. If **26.04**, either:

- Reinstall the PC with **Ubuntu 24.04 LTS Server**, **or**
- Use cPanel hosting / SES for email only (see SIMPLE_EMAIL.md)

### 2.2 Set hostname (FQDN)

```bash
sudo hostnamectl set-hostname mail.cheradip.com
# or: server.cheradip.com — must match a DNS A record pointing to your public IP
```

Add DNS **A** record: `mail.cheradip.com` → your **public** IP (grey cloud on Cloudflare).

### 2.3 Update system

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates wget curl lsb-release
```

### 2.4 Stop services that conflict (if reinstalling on existing box)

```bash
sudo systemctl stop nginx postfix opendkim 2>/dev/null || true
sudo systemctl disable nginx 2>/dev/null || true
```

HestiaCP installs its own nginx/apache, mail, mysql stack.

---

## Part 3 — Install HestiaCP

```bash
cd /root
wget https://raw.githubusercontent.com/hestiacp/hestiacp/release/install/hst-install.sh
```

### Option A — Interactive (easiest)

```bash
sudo bash hst-install.sh
```

Answer prompts:

- Continue? **y**
- Admin email: **your@gmail.com**
- Hostname: **mail.cheradip.com** (or FQDN you set in DNS)
- Install components: say **yes** to **nginx**, **php**, **mysql/mariadb**, **exim** (mail), **dovecot**, **fail2ban**
- Reboot when asked

### Option B — Non-interactive (copy, edit passwords, then run)

```bash
sudo bash hst-install.sh \
  --lang en \
  --hostname mail.cheradip.com \
  --email sashafik.me@gmail.com \
  --username admin \
  --password 'PickAStrongAdminPassword123!' \
  --port 8083 \
  --nginx yes \
  --apache no \
  --phpfpm yes \
  --multiphp yes \
  --named no \
  --mysql yes \
  --postgresql no \
  --exim yes \
  --dovecot yes \
  --sieve yes \
  --clamav no \
  --spamassassin no \
  --iptables yes \
  --fail2ban yes \
  --quota no \
  --api yes \
  --interactive no \
  --force
```

**Change** `--password` and `--email` before running.

Install takes **15–45 minutes**. Server **reboots** at the end.

---

## Part 4 — Firewall and router

On the server:

```bash
sudo ufw allow 8083/tcp comment 'HestiaCP panel'
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 25/tcp
sudo ufw allow 587/tcp
sudo ufw allow 465/tcp
sudo ufw allow 993/tcp
sudo ufw reload
```

On your **home router**: forward the same ports to `192.168.0.102` (your PC’s LAN IP).

---

## Part 5 — Log in to HestiaCP

Browser:

```text
https://YOUR_PUBLIC_IP:8083
```

Or (after DNS):

```text
https://mail.cheradip.com:8083
```

Login: user **`admin`** (or what you set) + password from install.

**Save** the install summary shown on screen (URL, user, password).

---

## Part 6 — Add cheradip.com and email

In HestiaCP web UI:

1. **User** → add user `sasha` (or use admin) if needed  
2. **Web** → **Add domain** → `cheradip.com`  
3. **Mail** → **Accounts** → add **`noreply@cheradip.com`** with a password  
4. **DNS** (if Hestia manages DNS) → add MX, SPF, or copy records to Cloudflare  
5. **SSL** → Let’s Encrypt for `cheradip.com` / `mail.cheradip.com` (optional for panel)

SMTP settings (typical):

| Setting | Value |
|---------|--------|
| Host | `mail.cheradip.com` |
| Port | 587 (TLS) or 465 (SSL) |
| User | `noreply@cheradip.com` |
| Password | from step 3 |

---

## Part 7 — Re-deploy your app (after Hestia)

Hestia owns ports 80/443. Options:

- Put **cheradip.com** site in Hestia’s web root and proxy `/ailt/api/` to port **8790**, **or**
- Run API on subdomain `api.cheradip.com` in Hestia + reverse proxy

Restore MySQL and app:

```bash
# Example — adjust paths to match Hestia user web directory
mysql -u root -p ailanguagetutor < ~/backup-ailanguagetutor.sql

cd /home/sasha/apps/cheradip/bcheradip   # or move under /home/user/web/
source /home/sasha/apps/cheradip/bcheradip/venv/bin/activate
pip install -r ailt_api/requirements.txt
sudo systemctl enable cheradip-ailt
sudo systemctl start cheradip-ailt
```

You may need to re-create `cheradip-ailt.service` and nginx proxy — plan this before install.

---

## Part 8 — ailt_api email (.env)

On the server:

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
```

```env
SMTP_ENABLED=true
SMTP_HOST=mail.cheradip.com
SMTP_PORT=587
SMTP_USER=noreply@cheradip.com
SMTP_PASSWORD=password-from-hestia-mail-account
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

If 587 fails, try port **465** with `SMTP_USE_SSL=true` and `SMTP_USE_TLS=false`.

Test:

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
sudo systemctl restart cheradip-ailt
./scripts/test_smtp.sh sashafik.me@gmail.com
```

---

## Part 9 — DNS checklist (Cloudflare / registrar)

| Type | Name | Value |
|------|------|--------|
| A | `@` or `cheradip.com` | your public IP |
| A | `mail` | your public IP |
| MX | `@` | `10 mail.cheradip.com` |
| TXT | `@` | `v=spf1 a mx ip4:YOUR_PUBLIC_IP ~all` |

Use **DNS only** (not proxied) for `mail` if you use Cloudflare.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Installer says unsupported OS | Use Ubuntu **24.04** — not 26 |
| Cannot open :8083 | `ufw allow 8083`; router port forward |
| Install conflicts / broken site | Restore from backup; prefer fresh Ubuntu 24.04 |
| SMTP auth failed | Full email as user; check password in Hestia |
| Gmail spam / reject | Complete SPF, DKIM in Hestia mail DNS |

View install log:

```bash
cat /root/hst_install_backups/*/hst-install-ubuntu.log 2>/dev/null | tail -50
```

---

## Summary

1. **HestiaCP = free**  
2. Need **Ubuntu 24.04** (not 26) for official support  
3. **Back up**, then run `hst-install.sh`  
4. Open **https://IP:8083**  
5. Create **noreply@cheradip.com**  
6. Put SMTP in **ailt_api `.env`**  
7. Test OTP email  

---

## If Ubuntu 26 blocks install

**Do not force on production without backup.** Safest paths:

1. **Dual boot / second disk** with Ubuntu 24.04 for Hestia, **or**  
2. **Keep Ubuntu 26** for app + use **cPanel hosting only for email** ([CPANEL_EMAIL.md](./CPANEL_EMAIL.md))
