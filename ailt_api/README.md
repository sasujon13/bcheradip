# AILT API on Linux (cheradip.com)

**Canonical backend** for the AI Language Tutor Android app — auth, billing, SMTP, language packs, cloud AI pool.

**Android client:** `D:\VSCode\android\ailanguagetutor` — see [`ANDROID_CLIENT.md`](ANDROID_CLIENT.md)

**Production email (Brevo):** [`deploy/BREVO_EMAIL.md`](deploy/BREVO_EMAIL.md)

## Public URL

```
https://cheradip.com/ailt/api/
```

Example: `GET https://cheradip.com/ailt/api/health`

## Quick verify (production)

```bash
curl -s https://cheradip.com/ailt/api/health
./scripts/test_smtp.sh your@email.com
```

## Database

MySQL schema **`ailanguagetutor`**. Django admin: **`ailt`** DB alias in `backend/settings.py`.

## Local dev (Windows)

```powershell
cd D:\VSCode\cheradip\bcheradip\ailt_api
.\scripts\run-dev.ps1
```

## Files

| Path | Purpose |
|------|---------|
| `app/` | FastAPI routers, models, SMTP |
| `.env` | Secrets (gitignored) — copy from `.env.production.example` |
| `deploy/cheradip-ailt.service` | systemd unit |
| `deploy/nginx-ailt-api.conf` | nginx `location /ailt/api/` |
| `promo-codes.example.json` | Seed promos on first start |
| `ai-providers.example.json` | Seed cloud AI providers |
| `packs/` | Language pack ZIPs (sync from Android pack-builder) |

## nginx (summary)

Public `/ailt/api/` → internal `127.0.0.1:8790/api/ailt/` — see `deploy/nginx-ailt-api.conf`.

**Home AI** (`https://ai.cheradip.com`) is **not** this service — it runs from the Android repo `server/v2/`.
