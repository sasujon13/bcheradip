#!/usr/bin/env pwsh
# Build PNG email assets (Gmail blocks inline SVG).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Assets = Join-Path $Root "app/assets/email"
$AndroidIcon = "D:\VSCode\android\ailanguagetutor\app\src\main\res\drawable-xxxhdpi\ic_launcher_foreground.png"

New-Item -ItemType Directory -Force -Path $Assets | Out-Null

if (Test-Path $AndroidIcon) {
    Copy-Item $AndroidIcon (Join-Path $Assets "cheradip-avatar.png") -Force
    Write-Host "Avatar: $Assets/cheradip-avatar.png"
} else {
    Write-Warning "Launcher icon not found: $AndroidIcon"
}

$svg = Join-Path $Assets "cheradip.svg"
$wordmark = Join-Path $Assets "cheradip-wordmark.png"
if ((Get-Command npx -ErrorAction SilentlyContinue) -and (Test-Path $svg)) {
    npx --yes @resvg/resvg-js-cli --fit-width 480 $svg $wordmark
    Write-Host "Wordmark: $wordmark"
}

Get-ChildItem $Assets -Filter "cheradip-*.png" | Format-Table Name, Length
