# Ensures ailt_api .venv exists with a working pip, then installs the package editable.
param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Invoke-VenvPip {
    param(
        [string[]]$Arguments,
        [switch]$QuietInstall
    )
    $Py = Join-Path $Root ".venv\Scripts\python.exe"
    $allArgs = @("-m", "pip") + $Arguments
    if ($QuietInstall) { $allArgs += "-q" }
    & $Py @allArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pip $($Arguments -join ' ') failed (exit $LASTEXITCODE)"
    }
}

function New-CloudApiVenv {
    if (Test-Path ".venv") {
        Write-Host "Removing broken ailt_api .venv..."
        Remove-Item -Recurse -Force ".venv"
    }
    Write-Host "Creating ailt_api virtual environment..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "python -m venv failed - install Python 3.11+ and ensure it is on PATH."
    }
}

function Bootstrap-Venv {
    param([switch]$QuietInstall)
    Invoke-VenvPip -Arguments @("install", "--upgrade", "pip", "setuptools", "wheel") -QuietInstall:$QuietInstall
    Invoke-VenvPip -Arguments @("install", "-e", ".") -QuietInstall:$QuietInstall
}

if (-not (Test-Path ".venv")) {
    New-CloudApiVenv
}

try {
    Bootstrap-Venv -QuietInstall:$Quiet
} catch {
    Write-Host $_.Exception.Message
    Write-Host "Recreating virtual environment and retrying..."
    New-CloudApiVenv
    Bootstrap-Venv -QuietInstall:$Quiet
}
