# AI Language Tutor — user manual (Angular route `/ailt`)

Builds **`ailt.html`** into the Angular app so **https://cheradip.com/ailt** works via the fcheradip router.

| Item | Path |
|------|------|
| Live URL | `https://cheradip.com/ailt` |
| Angular route | `fcheradip/src/app/app-routing.module.ts` → `path: 'ailt'` |
| Built HTML + assets | `fcheradip/src/assets/ailt/ailt.html` |
| Source manual | `D:\VSCode\android\ailanguagetutor\docs\manuals\USER_MANUAL.md` |
| App API | `../ailt_api/` → `https://cheradip.com/ailt/api/` |

## Build

```powershell
cd D:\VSCode\cheradip\bcheradip\ailt
.\scripts\build-manual.ps1
```

Output:

- `fcheradip/src/assets/ailt/ailt.html`
- `fcheradip/src/assets/ailt/manual.css`
- `fcheradip/src/assets/ailt/cheradip.svg`

## Test locally

```powershell
cd D:\VSCode\cheradip\fcheradip
ng serve
```

Open **http://localhost:4200/ailt**

Or preview the static file only:

```powershell
start D:\VSCode\cheradip\fcheradip\src\assets\ailt\ailt.html
```

## Deploy (production)

1. Run `build-manual.ps1` after editing `USER_MANUAL.md`
2. Build Angular: `ng build --configuration production`
3. Deploy `dist/frontend` as usual for cheradip.com

**Note:** `/ailt` is served by Angular (SPA). `/ailt/api/` is still proxied to FastAPI — keep the nginx API block from `ailt_api/deploy/nginx-ailt-api.conf`. Do **not** add a separate static `location /ailt/` alias (it would conflict).

## Files in this folder

| Path | Purpose |
|------|---------|
| `assets/manual.css` | Source styles (copied into fcheradip on build) |
| `assets/cheradip.svg` | Logo |
| `scripts/build-manual.py` | MD → `ailt.html` builder |
