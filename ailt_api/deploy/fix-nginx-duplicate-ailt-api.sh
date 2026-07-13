#!/usr/bin/env bash
# Remove duplicate `location /ailt/api/` blocks (inline + snippet include).
# Run on Linux: sudo bash ailt_api/deploy/fix-nginx-duplicate-ailt-api.sh
#
# Error this fixes:
#   duplicate location "/ailt/api/" in /etc/nginx/snippets/ailt-api-location.conf

set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

SITE="${NGINX_SITE_FILE:-/etc/nginx/sites-available/cheradip}"
if [[ ! -f "$SITE" ]]; then
  echo "Site file not found: $SITE"
  echo "Run: sudo bash ailt_api/deploy/find-nginx-site.sh"
  exit 1
fi

SNIPPET="/etc/nginx/snippets/ailt-api-location.conf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /etc/nginx/snippets
cp "${SCRIPT_DIR}/snippets/ailt-api-location.conf" "$SNIPPET"

backup="${SITE}.bak.$(date +%Y%m%d%H%M%S)"
cp "$SITE" "$backup"
echo "Backup: $backup"

python3 - "$SITE" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

# Drop inline location /ailt/api/ { ... } blocks (keep snippet include only).
pattern = re.compile(
    r"^[ \t]*location[ \t]+/ailt/api/[ \t]*\{.*?\n^[ \t]*\}[ \t]*\n?",
    re.MULTILINE | re.DOTALL,
)
new_text, n = pattern.subn("", text)

# Ensure exactly one include line inside server block (dedupe repeated includes).
include = "    include snippets/ailt-api-location.conf;"
lines = new_text.splitlines()
out: list[str] = []
seen_include = False
in_server = False
inserted = False
for i, line in enumerate(lines):
    if re.match(r"^[ \t]*server[ \t]*\{", line):
        in_server = True
    if in_server and re.match(r"^[ \t]*location[ \t]+/[ \t]*\{", line) and not inserted and not seen_include:
        out.append(include)
        inserted = True
        seen_include = True
    if "include snippets/ailt-api-location.conf" in line:
        if seen_include:
            continue
        seen_include = True
        out.append(include)
        continue
    out.append(line)
    if in_server and re.match(r"^[ \t]*\}[ \t]*$", line):
        if not inserted and not seen_include:
            out.insert(len(out) - 1, include)
            inserted = True
            seen_include = True
        in_server = False

final = "\n".join(out)
if not final.endswith("\n"):
    final += "\n"
path.write_text(final, encoding="utf-8")
print(f"Removed {n} inline /ailt/api/ block(s); snippet include kept.")
PY

echo "Testing nginx..."
nginx -t
systemctl reload nginx
echo "OK  nginx reloaded"
echo ""
bash "${SCRIPT_DIR}/diagnose-nginx-ailt.sh"
