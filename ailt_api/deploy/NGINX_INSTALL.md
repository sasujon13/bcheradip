# Where to put the `/ailt/api/` nginx block

The snippet in `nginx-ailt-api.conf` is **not** copied automatically by git deploy.
It must live in **nginx on your Linux server** (same machine as `/var/www/cheradip/`).

Your deploy path (from `fcheradip/Running Remote Project.txt`):

```text
/home/sasha/apps/cheradip/   ← git repos
/var/www/cheradip/           ← Angular static files (index.html)
127.0.0.1:8790               ← cheradip-ailt (FastAPI)
```

Until nginx proxies `/ailt/api/` → port 8790, [https://cheradip.com/ailt/api/health](https://cheradip.com/ailt/api/health) returns the Angular homepage (Cheradip HTML).

**User-facing manual (email links):** [https://cheradip.com/ailt](https://cheradip.com/ailt) — stays on Angular; **do not** proxy `/ailt` in nginx, only `/ailt/api/`.

---

## Option A — Automated (recommended)

SSH into the server, then:

```bash
cd /home/sasha/apps/cheradip/bcheradip
git pull origin main
sudo bash ailt_api/deploy/install-nginx-ailt-api.sh
```

The script:

1. Copies the location block to `/etc/nginx/snippets/ailt-api-location.conf`
2. Finds the enabled site that serves `cheradip.com`
3. Adds `include snippets/ailt-api-location.conf;` **before** `location /` if missing
4. Runs `nginx -t` and reloads nginx

---

## Option B — Manual (find the file yourself)

### 1. SSH to the server

```bash
ssh sasha@YOUR_SERVER_IP
```

### 2. Find which file defines cheradip.com

```bash
sudo grep -r "cheradip.com" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null
```

Typical results on Ubuntu:

| Path | Notes |
|------|--------|
| `/etc/nginx/sites-enabled/cheradip` | symlink → `sites-available/cheradip` |
| `/etc/nginx/sites-enabled/default` | sometimes used for everything |
| `/etc/nginx/conf.d/cheradip.conf` | on some setups |

Open the file that contains `server_name cheradip.com` (or `www.cheradip.com`):

```bash
sudo nano /etc/nginx/sites-available/cheradip
# or whatever path grep showed
```

### 3. Paste the block **inside** `server { ... }`, **above** `location /`

```nginx
server {
    listen 443 ssl;
    server_name cheradip.com www.cheradip.com;

    root /var/www/cheradip;
    index index.html;

    # === ADD THIS BLOCK HERE (before location /) ===
    location /ailt/api/ {
        proxy_pass http://127.0.0.1:8790/api/ailt/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        client_max_body_size 32m;
    }
    # === END ADD ===

    location / {
        try_files $uri $uri/ /index.html;   # Angular — must stay AFTER /ailt/api/
    }
}
```

**Order matters.** If `location /` comes first, `/ailt/api/health` is served as Angular `index.html`.

### 4. Test and reload

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Verify API (not HTML)

```bash
curl -s http://127.0.0.1:8790/api/ailt/health | head -c 120
curl -s https://cheradip.com/ailt/api/health | head -c 120
```

You want JSON like `{"status":"ok","service":"cheradip-ailt-api",...}` — not `<!doctype html>`.

If localhost works but public URL still returns HTML, nginx was not reloaded or the wrong `server { }` block was edited (e.g. HTTP vs HTTPS).

---

## Option C — Include snippet (clean, no huge edits)

```bash
sudo cp /home/sasha/apps/cheradip/bcheradip/ailt_api/deploy/nginx-ailt-api.conf \
        /etc/nginx/snippets/ailt-api-location.conf
```

Edit your cheradip `server { }` and add **one line** before `location /`:

```nginx
    include snippets/ailt-api-location.conf;
```

Then `sudo nginx -t && sudo systemctl reload nginx`.

---

## Also check FastAPI is running

```bash
sudo systemctl status cheradip-ailt
sudo systemctl start cheradip-ailt   # if inactive
journalctl -u cheradip-ailt -n 30 --no-pager
```

---

## Angular vs API (no fcheradip code change)

| URL | Served by |
|-----|-----------|
| `https://cheradip.com/ailt` | Angular (`path: 'ailt'`) |
| `https://cheradip.com/ailt/api/*` | FastAPI via nginx only |

Reference full server block: `nginx-cheradip-com.conf` in this folder.
