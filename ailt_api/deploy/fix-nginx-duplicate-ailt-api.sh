#!/usr/bin/env bash
# Fix broken /ailt/api/ nginx placement:
#   - duplicate location "/ailt/api/"
#   - location "/ailt/api/" is outside location "/api/"  (include nested wrong)
#
# Run on Linux: sudo bash ailt_api/deploy/fix-nginx-duplicate-ailt-api.sh

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

# Drop inline location /ailt/api/ { ... } blocks.
pattern = re.compile(
    r"^[ \t]*location[ \t]+/ailt/api/[ \t]*\{.*?\n^[ \t]*\}[ \t]*\n?",
    re.MULTILINE | re.DOTALL,
)
text, n_inline = pattern.subn("", text)

# Drop every existing ailt snippet include (may be nested wrongly inside /api/).
include = "    include snippets/ailt-api-location.conf;"
text, n_inc = re.subn(
    r"^[ \t]*include[ \t]+snippets/ailt-api-location\.conf;[ \t]*\n?",
    "",
    text,
    flags=re.MULTILINE,
)

lines = text.splitlines()
out: list[str] = []
depth = 0  # global { } depth
inserted = False


def is_catch_all_location(line: str) -> bool:
    # Exact "location / {" only — not /api/, /static/, etc.
    return bool(re.match(r"^[ \t]*location[ \t]+/[ \t]*\{", line))


for line in lines:
    # Server top-level is depth == 1 (inside one server { }).
    if depth == 1 and is_catch_all_location(line) and not inserted:
        out.append(include)
        inserted = True
    out.append(line)
    depth += line.count("{") - line.count("}")

if not inserted:
    # Fallback: insert before the closing } of the first server block (depth 1 -> 0).
    final = []
    depth = 0
    for line in out:
        delta = line.count("{") - line.count("}")
        if depth == 1 and delta < 0 and not inserted:
            final.append(include)
            inserted = True
        final.append(line)
        depth += delta
    out = final

final = "\n".join(out)
if not final.endswith("\n"):
    final += "\n"
path.write_text(final, encoding="utf-8")
print(
    f"Removed {n_inline} inline /ailt/api/ block(s), "
    f"{n_inc} misplaced include(s); "
    f"snippet include at server level: {inserted}"
)
PY

echo "Testing nginx..."
nginx -t
systemctl start nginx 2>/dev/null || systemctl reload nginx
echo "OK  nginx started/reloaded"
echo ""
bash "${SCRIPT_DIR}/diagnose-nginx-ailt.sh"
