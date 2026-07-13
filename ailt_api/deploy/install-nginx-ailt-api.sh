#!/usr/bin/env bash
# Install /ailt/api/ nginx proxy on cheradip.com (Ubuntu).
# Idempotent — safe on every deploy.
#
# Run: sudo bash ailt_api/deploy/install-nginx-ailt-api.sh
# Optional: sudo NGINX_SITE_FILE=/path/to/site.conf bash ailt_api/deploy/install-nginx-ailt-api.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNIPPET_SRC="${SCRIPT_DIR}/snippets/ailt-api-location.conf"
SNIPPET_DST="/etc/nginx/snippets/ailt-api-location.conf"
NORMALIZE="${SCRIPT_DIR}/normalize_ailt_api_site.py"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

if [[ ! -f "$SNIPPET_SRC" ]]; then
  echo "Missing $SNIPPET_SRC"
  exit 1
fi
if [[ ! -f "$NORMALIZE" ]]; then
  echo "Missing $NORMALIZE"
  exit 1
fi

discover_site_files() {
  local -a found=()
  local f real

  if [[ -n "${NGINX_SITE_FILE:-}" && -f "$NGINX_SITE_FILE" ]]; then
    echo "$NGINX_SITE_FILE"
    return 0
  fi

  while IFS= read -r f; do
    found+=("$f")
  done < <(
    grep -rlE "cheradip\.com|/var/www/cheradip" /etc/nginx 2>/dev/null | sort -u
  )

  if [[ ${#found[@]} -eq 0 ]]; then
    while IFS= read -r f; do
      found+=("$f")
    done < <(
      grep -rl "try_files.*index\.html" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | sort -u
    )
  fi

  if [[ ${#found[@]} -eq 0 ]]; then
    while IFS= read -r f; do
      [[ -f "$f" ]] && found+=("$f")
    done < <(ls -1 /etc/nginx/sites-enabled/* 2>/dev/null | sort -u)
  fi

  local -a ssl_files=()
  for f in "${found[@]}"; do
    real="$(readlink -f "$f" 2>/dev/null || echo "$f")"
    if grep -qE "listen[[:space:]]+443|ssl_certificate" "$real" 2>/dev/null; then
      ssl_files+=("$real")
    fi
  done

  if [[ ${#ssl_files[@]} -gt 0 ]]; then
    for real in "${ssl_files[@]}"; do
      if [[ "$real" == *"/sites-available/cheradip" ]] || [[ "$real" == *"/sites-enabled/cheradip" ]]; then
        echo "$real"
        return 0
      fi
    done
    printf '%s\n' "${ssl_files[@]}" | sort -u
    return 0
  fi

  for f in "${found[@]}"; do
    readlink -f "$f" 2>/dev/null || echo "$f"
  done | sort -u
}

echo "Installing snippet -> $SNIPPET_DST"
mkdir -p /etc/nginx/snippets
cp "$SNIPPET_SRC" "$SNIPPET_DST"

echo "Discovering nginx site file(s)..."
mapfile -t SITE_FILES < <(discover_site_files)

if [[ ${#SITE_FILES[@]} -eq 0 ]]; then
  echo ""
  echo "ERROR: Could not find nginx site config automatically."
  echo "Run: sudo bash ailt_api/deploy/find-nginx-site.sh"
  echo "Then re-run with:"
  echo "  sudo NGINX_SITE_FILE=/etc/nginx/sites-available/YOURFILE bash ailt_api/deploy/install-nginx-ailt-api.sh"
  exit 1
fi

echo "Candidate file(s):"
printf '  %s\n' "${SITE_FILES[@]}"

patched=0
for real in "${SITE_FILES[@]}"; do
  [[ -f "$real" ]] || continue
  # Skip unrelated files that only mention cheradip in a comment
  if ! grep -qE "server_name.*cheradip|/var/www/cheradip|try_files" "$real" 2>/dev/null; then
    continue
  fi
  backup="${real}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$real" "$backup"
  echo "Normalizing $real (backup: $backup)"
  python3 "$NORMALIZE" "$real"
  patched=1
done

if [[ $patched -eq 0 ]]; then
  echo "ERROR: Could not patch any site file."
  exit 1
fi

echo "Testing nginx config..."
nginx -t

echo "Starting/reloading nginx..."
if systemctl is-active --quiet nginx; then
  systemctl reload nginx
else
  systemctl start nginx
fi

echo ""
bash "${SCRIPT_DIR}/diagnose-nginx-ailt.sh"
