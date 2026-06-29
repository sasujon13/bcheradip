# Linux deploy — AILT App API + your existing Cheradip deploy

This doc extends your normal **bcheradip + fcheradip** deploy. The Django `cheradip` service is unchanged; **ailt_api** is a second systemd service on port **8790**.

## One-time setup (Linux)

### 1. MySQL

Database **`ailanguagetutor`** must exist (you synced via `mysql_db_sync`). Grant your DB user access:

```sql
GRANT ALL ON ailanguagetutor.* TO 'cheradip_cheradip'@'localhost';
FLUSH PRIVILEGES;
```

### 2. ailt_api `.env`

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
cp .env.production.example .env
nano .env   # DATABASE_URL, ADMIN_SEED_PASSWORD, SMTP_*, API keys
chmod 600 .env
```

**DATABASE_URL example:**

```env
DATABASE_URL=mysql+pymysql://cheradip_cheradip:YOUR_PASS@127.0.0.1:3306/ailanguagetutor?charset=utf8mb4
```

### 3. Python deps (same venv as Django)

```bash
cd /home/sasha/apps/cheradip/bcheradip
source venv/bin/activate
pip install -r ailt_api/requirements.txt
```

### 4. systemd

```bash
sudo cp /home/sasha/apps/cheradip/bcheradip/ailt_api/deploy/cheradip-ailt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cheradip-ailt
sudo systemctl start cheradip-ailt
```

Adjust `User=` / paths in the unit file if your home directory differs.

### 5. nginx

Add the block from `ailt_api/deploy/nginx-ailt-api.conf` inside your **cheradip.com** `server { }` (before `location /`).

Add **email logo PNGs** (same place, before `location /`):

```bash
# Paste contents of ailt_api/deploy/nginx-email-assets.conf into nginx site config
sudo nginx -t
sudo systemctl reload nginx
curl -sI https://cheradip.com/assets/email/cheradip-wordmark.png | head -1
# HTTP/2 200 — required for HTML email logos
```

Why not Angular `/assets/email/` alone? Production `ng build` **hashes filenames** (`cheradip-wordmark.abc123.png`), and the SPA **fallback serves index.html** for unknown paths — so fixed email URLs break. Nginx serves stable PNG names directly from `ailt_api/app/assets/email/`.

Fallback without nginx change: `EMAIL_ASSETS_BASE_URL=https://cheradip.com/ailt/api/assets/email` in `.env`.

### 6. Verify

```bash
curl -s http://127.0.0.1:8790/api/ailt/health | python3 -m json.tool
curl -s https://cheradip.com/ailt/api/health | python3 -m json.tool
```

Expect `"database":"ailanguagetutor"`, `"smtp_enabled":true`.

### 7. Test OTP email

Configure Brevo in `.env` (see [BREVO_EMAIL.md](BREVO_EMAIL.md)), then:

```bash
cd /home/sasha/apps/cheradip/bcheradip/ailt_api
chmod +x scripts/test_smtp.sh
./scripts/test_smtp.sh sashafik.me@gmail.com
```

---

## Every deploy (updated script)

Replace your backend section with:

```bash
# --- Backend (Django + AILT API) ---
cd /home/sasha/apps/cheradip/bcheradip
git fetch origin
git checkout main
git pull origin main
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r ailt_api/requirements.txt
python manage.py collectstatic --noinput
sudo systemctl restart cheradip
sudo systemctl restart cheradip-ailt

# --- Frontend (unchanged) ---
cd /home/sasha/apps/cheradip/fcheradip
git fetch origin
git checkout main
git pull origin main
npm ci
npm run build -- --configuration production

FRONT_DIST="/home/sasha/apps/cheradip/fcheradip/dist/frontend"
if [ -f "$FRONT_DIST/index.html" ]; then
  sudo rsync -av --delete "$FRONT_DIST/" /var/www/cheradip/
elif [ -f "$FRONT_DIST/browser/index.html" ]; then
  sudo rsync -av --delete "$FRONT_DIST/browser/" /var/www/cheradip/
else
  find /home/sasha/apps/cheradip/fcheradip/dist -name index.html
fi

sudo systemctl reload nginx
sudo systemctl status cheradip cheradip-ailt nginx --no-pager

# Quick health
curl -s https://cheradip.com/ailt/api/health | head -c 200
echo
```

---

## Email (OTP verification codes)

**→ [BREVO_EMAIL.md](BREVO_EMAIL.md)** — Brevo SMTP, `Cheradip <noreply@cheradip.com>`.

```bash
bash scripts/setup-brevo-env.sh   # first time
./scripts/test_smtp.sh your@gmail.com
sudo systemctl restart cheradip-ailt
```

---

## Language packs

Packs are **not** in git (too large). After deploy, either:

- Sync from your PC: run Android `tools/pack-builder/scripts/build-all-packs.ps1` (writes to `ailt_api/packs/`), then `rsync` to server, **or**
- Rely on rows already in MySQL from prior sync.

Restart API after adding packs: `sudo systemctl restart cheradip-ailt`

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `502` on `/ailt/api/health` | `sudo systemctl status cheradip-ailt` — check `.env` DATABASE_URL |
| DB connection refused | MySQL running; user has `ailanguagetutor` grant |
| SMTP auth failed | Brevo **SMTP key** as password; Login as `SMTP_USER` — [BREVO_EMAIL.md](BREVO_EMAIL.md) |
| OTP not received | `./scripts/diagnose_smtp.sh`; verify sender in Brevo dashboard |
| 404 on `/ailt/api/` | nginx snippet missing or wrong `proxy_pass` |

Logs: `journalctl -u cheradip-ailt -f`
