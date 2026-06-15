# Initialize MySQL database (XAMPP must be running)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - set ADMIN_SEED_PASSWORD and DATABASE_URL if needed."
}

$RepoEnv = Join-Path (Split-Path -Parent (Split-Path -Parent $Root)) "local.env.properties"
if (Test-Path $RepoEnv) {
    Get-Content $RepoEnv | ForEach-Object {
        if ($_ -match '^\s*ADMIN_SEED_PASSWORD=(.+)$') {
            $env:ADMIN_SEED_PASSWORD = $matches[1].Trim()
        }
    }
}

& (Join-Path $Root "scripts\ensure-venv.ps1") -Quiet
& .\.venv\Scripts\python.exe scripts\init_db.py
