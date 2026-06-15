# Start local cheradip.com/api/ailt dev API (port 8790)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Port = 8790
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Write-Host "Port $Port is already in use (PID $($existing.OwningProcess))."
    Write-Host "API is probably already running -> http://127.0.0.1:${Port}/api/ailt/health"
    Write-Host ""
    Write-Host "To restart, stop the old process first:"
    Write-Host "  Stop-Process -Id $($existing.OwningProcess) -Force"
    exit 0
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env - edit DATABASE_URL / ADMIN_SEED_PASSWORD if needed."
}

& (Join-Path $Root "scripts\ensure-venv.ps1") -Quiet

# Load admin password from repo local.env.properties if present
$EnvFile = Join-Path (Split-Path -Parent (Split-Path -Parent $Root)) "local.env.properties"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*ADMIN_SEED_PASSWORD=(.+)$') {
            $env:ADMIN_SEED_PASSWORD = $matches[1].Trim()
        }
    }
}

Write-Host "Requires XAMPP MySQL + database ailanguagetutor (run scripts\init-db.ps1 once)."
Write-Host ('AILT API (MySQL) -> http://127.0.0.1:8790/api/ailt/health')
& .\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8790 --reload
