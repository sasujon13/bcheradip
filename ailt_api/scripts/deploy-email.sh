#!/usr/bin/env bash
# Deploy branded OTP email (v4) from origin/main — safe when local branch diverged.
# Run from bcheradip repo root, OR pipe from GitHub when scripts are missing:
#   curl -fsSL "https://raw.githubusercontent.com/sasujon13/bcheradip/main/ailt_api/scripts/deploy-email.sh" | bash
set -euo pipefail

ROOT="${BCHERADIP_ROOT:-$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd || pwd)}"
if [[ ! -d "$ROOT/.git" ]]; then
  ROOT="/home/sasha/apps/cheradip/bcheradip"
fi
cd "$ROOT"

echo "==> Repo: $ROOT"
git fetch origin

FILES=(
  ailt_api/app/services/email_templates.py
  ailt_api/app/services/email_service.py
  ailt_api/app/main.py
  ailt_api/app/config.py
  ailt_api/app/assets/email/cheradip.svg
  ailt_api/app/assets/email/cheradip-avatar.png
  ailt_api/app/assets/email/cheradip-wordmark.png
  ailt_api/scripts/build-email-assets.sh
  ailt_api/scripts/sync-email-from-origin.sh
  ailt_api/scripts/test_smtp.py
  ailt_api/scripts/test_smtp.sh
  ailt_api/scripts/deploy-email.sh
  ailt_api/deploy/BREVO_EMAIL.md
  ailt_api/deploy/BIMI_INBOX_LOGO.md
)

echo "==> Checkout email files from origin/main"
git checkout origin/main -- "${FILES[@]}"

if [[ ! -f ailt_api/scripts/build-email-assets.sh ]]; then
  echo "ERROR: checkout failed — is $ROOT the bcheradip git repo?" >&2
  exit 1
fi

echo "==> Build PNG assets (avatar + wordmark)"
bash ailt_api/scripts/build-email-assets.sh

echo "==> Restart API"
sudo systemctl restart cheradip-ailt
sleep 2

echo "==> Health check"
HEALTH="$(curl -sf http://127.0.0.1:8790/api/ailt/health 2>/dev/null || true)"
if [[ -z "$HEALTH" ]]; then
  echo "WARN: health endpoint returned empty — API may be down:" >&2
  sudo systemctl status cheradip-ailt --no-pager -l | tail -20
  echo "Recent logs:" >&2
  journalctl -u cheradip-ailt -n 30 --no-pager >&2 || true
else
  echo "$HEALTH" | python3 -m json.tool
fi

echo "==> Public logo URLs"
curl -sI "https://cheradip.com/ailt/api/assets/email/cheradip-avatar.png" | head -1 || true
curl -sI "https://cheradip.com/ailt/api/assets/email/cheradip-wordmark.png" | head -1 || true

echo "==> Template on disk"
grep -n "OTP_TEMPLATE_VERSION" ailt_api/app/services/email_templates.py | head -1

echo ""
echo "Done. Send test email:"
echo "  cd ailt_api && bash scripts/test_smtp.sh your@gmail.com"
echo "Expect: Template version: otp-html-v4"
