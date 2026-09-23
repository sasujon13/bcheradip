# bcheradip — Agent Guide

## Projects on this server

| Component | Path | URL |
|-----------|------|-----|
| **Cheradip MCQ site (Django)** | `cheradip/` | `https://cheradip.com/api/` |
| **AILT App API (FastAPI)** | `ailt_api/` | `https://cheradip.com/ailt/api/` |
| **AILT user manual (static)** | `ailt/` → `fcheradip/src/assets/ailt/ailt.html` | `https://cheradip.com/ailt` |
| **Android client** | *external* | see below |

## AILT App API (`ailt_api/`)

Backend for **AI Language Tutor** Android app: auth, OTP/SMTP, billing, promo, referral, language packs, cloud AI pool.

- **Run locally:** `cd ailt_api; .\scripts\run-dev.ps1`
- **Deploy:** `ailt_api/README.md`
- **Database:** MySQL `ailanguagetutor`
- **Do not break:** existing Django routes at `/api/` — AILT is mounted separately at `/ailt/api/` via nginx

When the user asks to update **AILT server**, **App API**, **auth**, **billing**, **SMTP**, or **cloud AI routes** → edit **`ailt_api/`** only unless they explicitly mean the main Cheradip MCQ site.

**Linux deploy:** `ailt_api/deploy/DEPLOY_LINUX.md`

## Linked Android project

| Item | Path |
|------|------|
| **Android repo** | `D:\VSCode\android\ailanguagetutor` |
| **API client (Retrofit)** | `ailanguagetutor/core/network/` |
| **Home AI (separate)** | `ailanguagetutor/server/v2/` |
| **Pack builder** | `ailanguagetutor/tools/pack-builder/` → syncs to `ailt_api/packs/` |

Details: `ailt_api/ANDROID_CLIENT.md`

## Django (existing — do not refactor for AILT)

- Main app: `cheradip/`
- URLs: `backend/urls.py` → `path('api/', include('cheradip.urls'))`
- DB aliases: `default`, `hsc`, `honours`, `job`, **`ailt`** (read-only admin view of `ailanguagetutor`), **`extcheradip`** (VS Code extension accounts)

New AILT work belongs in **`ailt_api/`**, not inside `cheradip/` views unless explicitly integrating with the main site.

## Shared accounts (Cheradip site ⇄ VS Code extension)

The website (`cheradip_customers`) and the extension (`extcheradip.ext_users`) keep **one account per user, with the same credentials**, and sync runs automatically — no user prompt, no re-registration:

| Direction | Code | Trigger |
|-----------|------|---------|
| site → extension | `cheradip/ext_account_sync.py` (`sync_customer_to_ext`) | signup, login, password change/reset, profile update |
| extension → site | `ailt_api/app/services/cheradip_account_sync.py` (`ensure_cheradip_account`) | `/ext/auth` signup, login, password/change, recovery/reset |

Password formats stay native to each system: the extension stores **bcrypt** (passlib), the website stores Django **`pbkdf2_sha256`**. Whenever the plaintext is known the target hash is re-derived; otherwise a `pbkdf2_sha256$…` hash is copied verbatim (passlib's context in `ailt_api/app/security.py` lists `django_pbkdf2_sha256` for exactly that). Mirroring is best-effort: it is wrapped in try/except on both sides and can never break sign-in.

- Env: `DATABASE_EXT_NAME` (Django, default `extcheradip`), `CHERADIP_DATABASE_URL` (FastAPI, default `root@127.0.0.1/cheradip_cheradip`)
- Login is country-agnostic: `CustomerRetrieveView` falls back to a plain `authenticate()` when the country-scoped lookup misses (usernames are globally unique)
