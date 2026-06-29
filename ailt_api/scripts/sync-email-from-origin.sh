#!/usr/bin/env bash
# Restore branded OTP email files from origin/main (when git pull diverged).
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"

echo "=== bcheradip email template sync ==="
echo "Repo: $ROOT"

git fetch origin

FILES=(
  ailt_api/app/services/email_templates.py
  ailt_api/app/services/email_service.py
  ailt_api/app/assets/email/cheradip.svg
  ailt_api/app/assets/email/cheradip-avatar.png
  ailt_api/app/assets/email/cheradip-wordmark.png
  ailt_api/app/main.py
  ailt_api/app/config.py
  ailt_api/scripts/test_smtp.py
  ailt_api/scripts/test_smtp.sh
  ailt_api/scripts/build-email-assets.sh
  ailt_api/deploy/BIMI_INBOX_LOGO.md
)

missing=0
for f in "${FILES[@]}"; do
  if ! git cat-file -e "origin/main:$f" 2>/dev/null; then
    echo "MISSING on origin/main: $f"
    missing=$((missing + 1))
  fi
done
if [[ $missing -gt 0 ]]; then
  echo "Push latest bcheradip from your PC first (git push origin main)."
  exit 1
fi

echo "Checking out template files from origin/main..."
git checkout origin/main -- "${FILES[@]}"

echo ""
echo "=== Verify ==="
grep -n "otp-html-v4" ailt_api/app/services/email_templates.py | head -1
ls -la ailt_api/app/assets/email/cheradip-avatar.png ailt_api/app/assets/email/cheradip-wordmark.png

echo ""
echo "Restart API:"
echo "  sudo systemctl restart cheradip-ailt"
echo "Test (use bash if Permission denied):"
echo "  cd ailt_api && bash scripts/test_smtp.sh your@gmail.com"
echo "Health (local first):"
echo "  curl -s http://127.0.0.1:8790/api/ailt/health | python3 -m json.tool"
echo "Health (public):"
echo "  curl -s https://cheradip.com/ailt/api/health | python3 -m json.tool | grep email_template"

chmod +x ailt_api/scripts/test_smtp.sh ailt_api/scripts/sync-email-from-origin.sh 2>/dev/null || true
