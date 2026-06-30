#!/usr/bin/env bash
# Install /ailt/api/ nginx proxy on cheradip.com (Ubuntu).
# Run on Linux server: sudo bash ailt_api/deploy/install-nginx-ailt-api.sh
#
# Optional: sudo NGINX_SITE_FILE=/path/to/site.conf bash ailt_api/deploy/install-nginx-ailt-api.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNIPPET_SRC="${SCRIPT_DIR}/snippets/ailt-api-location.conf"
SNIPPET_DST="/etc/nginx/snippets/ailt-api-location.conf"
INCLUDE_LINE='    include snippets/ailt-api-location.conf;'

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

if [[ ! -f "$SNIPPET_SRC" ]]; then
  echo "Missing $SNIPPET_SRC"
  exit 1
fi

discover_site_files() {
  local -a found=()
  local f real

  # Explicit override
  if [[ -n "${NGINX_SITE_FILE:-}" && -f "$NGINX_SITE_FILE" ]]; then
    echo "$NGINX_SITE_FILE"
    return 0
  fi

  # Search all nginx config (not only sites-enabled)
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

  # Prefer HTTPS / ssl blocks' source files
  local -a ssl_files=()
  for f in "${found[@]}"; do
    real="$(readlink -f "$f" 2>/dev/null || echo "$f")"
    if grep -qE "listen[[:space:]]+443|ssl_certificate" "$real" 2>/dev/null; then
      ssl_files+=("$real")
    fi
  done

  if [[ ${#ssl_files[@]} -gt 0 ]]; then
    printf '%s\n' "${ssl_files[@]}" | sort -u
    return 0
  fi

  for f in "${found[@]}"; do
    readlink -f "$f" 2>/dev/null || echo "$f"
  done | sort -u
}

patch_site_file() {
  local real="$1"

  if grep -q "ailt/api" "$real" 2>/dev/null; then
    echo "OK  $real already has /ailt/api/ proxy"
    return 0
  fi
  if grep -qF "include snippets/ailt-api-location.conf" "$real" 2>/dev/null; then
    echo "OK  $real already includes ailt-api snippet"
    return 0
  fi

  echo "Patching $real ..."
  local backup="${real}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$real" "$backup"
  echo "  backup: $backup"

  awk -v inc="$INCLUDE_LINE" '
    BEGIN { in_server=0; done=0 }
    /^[[:space:]]*server[[:space:]]*\{/ { in_server=1 }
    in_server && /location[[:space:]]+\/[[:space:]]*\{/ && !done {
      print inc
      done=1
    }
    { print }
    in_server && /^[[:space:]]*\}/ {
      if (!done) {
        print inc
        done=1
      }
      in_server=0
    }
    END {
      if (!done) {
        print inc
      }
    }
  ' "$backup" > "${real}.tmp"
  mv "${real}.tmp" "$real"
  echo "  added: include snippets/ailt-api-location.conf"
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
  patch_site_file "$real"
  patched=1
done

if [[ $patched -eq 0 ]]; then
  echo "ERROR: Could not patch any site file."
  exit 1
fi

echo "Testing nginx config..."
nginx -t

echo "Reloading nginx..."
systemctl reload nginx

echo ""
bash "${SCRIPT_DIR}/diagnose-nginx-ailt.sh"
