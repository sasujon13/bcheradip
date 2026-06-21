# Install a control panel on your home Linux server

You want **cPanel** at `https://cheradip.com:2083` on the PC that runs cheradip.com.

Read this **before** installing — wrong OS or a messy install can break your current site and API.

---

## Important facts

| Item | Your situation |
|------|----------------|
| Your OS | **Ubuntu 26.04** (from server logs) |
| cPanel supports | **Ubuntu 24.04 LTS**, AlmaLinux 8/9/10, Rocky 8/9 — **not Ubuntu 26** |
| cPanel license | **Paid** (~$15–45/month for VPS) — [cpanel.net/pricing](https://cpanel.net/pricing/) |
| Current services | nginx, Django `cheradip`, `ailt_api`, MySQL — **cPanel takes over** Apache/nginx, mail, DNS |
| Home network | IP `192.168.0.102` — you need **router port forwarding** for 2083, 80, 443 |

**Official cPanel on Ubuntu 26 = not supported.** Do not run the cPanel installer on Ubuntu 26.

---

## Choose one path

### Path A — Official cPanel (what you asked for)

**Requires a clean supported OS.** Best on a **new disk / new VM**, not “install on top of” your working Ubuntu 26 server.

1. **Back up everything** (MySQL, `/home/sasha/apps/cheradip`, nginx configs, `.env` files).
2. **Reinstall the server** with one of:
   - **AlmaLinux 10** (recommended for cPanel), or
   - **Ubuntu 24.04 LTS Server** (minimal install)
3. Buy a **cPanel license** (trial available for first install).
4. Run cPanel’s official installer (as root):

```bash
# AlmaLinux or Ubuntu 24.04 ONLY — not Ubuntu 26
cd /home && curl -o latest -L https://securedownloads.cpanel.net/latest && sh latest
```

Install takes 30–90 minutes.

5. Open firewall:

```bash
# firewalld (AlmaLinux) or ufw (Ubuntu)
# WHM/cPanel needs: 2083, 2087, 2089, 80, 443, 25, 587, 465, 993, 995, etc.
```

6. Access:
   - **WHM (admin):** `https://YOUR_PUBLIC_IP:2087`
   - **cPanel (users):** `https://YOUR_PUBLIC_IP:2083`
   - For `https://cheradip.com:2083`: DNS **A** record `cheradip.com` → your **public** IP, router forwards **2083** to this PC.

7. In WHM → create account for **cheradip.com** → **Email Accounts** → `noreply@cheradip.com`.

8. **Re-deploy** your app (Django + ailt_api) — cPanel uses its own web stack; you may run the API on a subdomain or a custom port behind nginx/Apache.

**Warning:** cPanel is built to manage the whole server. Mixing it with a hand-built nginx + systemd setup is painful. Prefer **fresh AlmaLinux + cPanel**, then migrate sites in.

Docs: [cPanel installation guide](https://docs.cpanel.net/installation-guide/)

---

### Path B — Free panel on Ubuntu 26 (easier on your current PC)

If you want a **cPanel-like UI** without reinstalling OS:

| Panel | OS | cPanel-like | Cost |
|-------|-----|-------------|------|
| **HestiaCP** | Ubuntu 22/24 (may work on 26) | Yes — web + email | Free |
| **CyberPanel** | Ubuntu | Yes | Free |
| **Webmin/Virtualmin** | Any Linux | Partial | Free |

Example — **HestiaCP** (simple):

```bash
# Ubuntu — check https://hestiacp.com/install.html for current one-liner
wget https://raw.githubusercontent.com/hestiacp/hestiacp/release/install/hst-install.sh
sudo bash hst-install.sh
```

Access: `https://YOUR_IP:8083` (not 2083 — different product).

Then create domain `cheradip.com`, email `noreply@cheradip.com`, use SMTP in `ailt_api/.env` as in [CPANEL_EMAIL.md](./CPANEL_EMAIL.md).

---

### Path C — Keep current server, cPanel elsewhere (simplest for email only)

- **Website + API** stay on your home Ubuntu server (as now).
- **Email only** on cheap **cPanel hosting** ($3–10/mo) — create `noreply@cheradip.com` there.
- Point **MX** records to that host; `.env` uses `mail.cheradip.com` SMTP.

No cPanel on your PC at all. See [CPANEL_EMAIL.md](./CPANEL_EMAIL.md).

---

## Home PC checklist (all paths)

1. **Static public IP** or **Dynamic DNS** (e.g. `cheradip.com` → home IP).
2. **Router port forward** to `192.168.0.102`:
   - 80, 443 (website)
   - 2083, 2087 (cPanel only if Path A)
   - 8790 (ailt_api — if exposed via nginx)
3. **ISP** must allow inbound 80/443 (some block residential servers).
4. **Backup power / UPS** optional but recommended.

---

## After you have mail in the panel (any path)

On your app server, `.env`:

```env
SMTP_ENABLED=true
SMTP_HOST=mail.cheradip.com
SMTP_PORT=587
SMTP_USER=noreply@cheradip.com
SMTP_PASSWORD=email-password-from-panel
SMTP_FROM=noreply@cheradip.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
DEV_LOG_OTP=false
```

```bash
sudo systemctl restart cheradip-ailt
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
./scripts/test_smtp.sh sashafik.me@gmail.com
```

---

## Recommendation for you

| Goal | Best choice |
|------|-------------|
| “I want real cPanel at :2083” | **Path A** — reinstall **AlmaLinux 10** or **Ubuntu 24.04**, license, clean install |
| “I want GUI on this Ubuntu 26 PC now” | **Path B** — **HestiaCP** |
| “I only need OTP email working” | **Path C** — cheap cPanel host for mail only |

---

## Do not do this

- Run cPanel installer on **Ubuntu 26** — unsupported, likely broken.
- Install cPanel on a server with production cheradip.com **without backup** — high risk.
- Expect `cheradip.com:2083` to work without **port 2083 forwarded** on your router.

If you tell us **Path A, B, or C**, we can give step-by-step commands for that path only.
