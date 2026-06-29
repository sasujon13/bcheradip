#!/usr/bin/env bash
# Build PNG email assets (Gmail blocks inline SVG).
set -euo pipefail
cd "$(dirname "$0")/.."
ASSETS="$(pwd)/app/assets/email"
ANDROID_ICON="${ANDROID_ICON:-$HOME/VSCode/android/ailanguagetutor/app/src/main/res/drawable-xxxhdpi/ic_launcher_foreground.png}"

mkdir -p "$ASSETS"

if [[ -f "$ANDROID_ICON" ]]; then
  cp "$ANDROID_ICON" "$ASSETS/cheradip-avatar.png"
  echo "Avatar: $ASSETS/cheradip-avatar.png"
else
  echo "WARN: Android launcher not found at $ANDROID_ICON"
fi

if command -v npx >/dev/null 2>&1 && [[ -f "$ASSETS/cheradip.svg" ]]; then
  npx --yes @resvg/resvg-js-cli --fit-width 480 "$ASSETS/cheradip.svg" "$ASSETS/cheradip-wordmark.png"
  echo "Wordmark: $ASSETS/cheradip-wordmark.png"
else
  echo "WARN: install Node/npx to regenerate cheradip-wordmark.png from SVG"
fi

ls -la "$ASSETS"/cheradip-avatar.png "$ASSETS"/cheradip-wordmark.png 2>/dev/null || true
