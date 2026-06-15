# Android client link

This API serves the **AI Language Tutor** Android app.

## Client repository

```
D:\VSCode\android\ailanguagetutor
```

## URLs

| Build | `API_BASE_URL` |
|-------|----------------|
| Release / default | `https://cheradip.com/ailt/api/` |
| Local emulator | `http://10.0.2.2:8790/api/ailt/` |

Home AI (not this service): `https://ai.cheradip.com` — implemented in Android repo `server/v2/`.

## Keep API in sync

When you change routes or JSON shapes in `app/routers/` or `app/schemas.py`, update the matching Kotlin files:

- `core/network/AiltApiService.kt` — Retrofit paths
- `core/network/*Models.kt` or inline DTOs — request/response types
- `core/auth/`, `core/billing/`, etc. — repositories

## Language packs

Built in the Android repo, synced here:

```powershell
cd D:\VSCode\android\ailanguagetutor
.\tools\pack-builder\scripts\build-all-packs.ps1
```

Output: `ailt_api/packs/{lang}/v1.zip`

## Agent instructions

- Server changes → this folder (`bcheradip/ailt_api`)
- App UI / client changes → Android repo
- Link doc on Android side: `docs/BCHERADIP_SERVER.md`
