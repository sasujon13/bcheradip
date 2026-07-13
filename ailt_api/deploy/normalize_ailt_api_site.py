#!/usr/bin/env python3
"""Normalize cheradip nginx site: one server-level /ailt/api/ snippet include.

Usage:
  sudo python3 normalize_ailt_api_site.py /etc/nginx/sites-available/cheradip

Idempotent: safe to run every deploy.
Fixes:
  - duplicate location "/ailt/api/"
  - include nested inside location /api/ (outside location error)
  - leftover inline location /ailt/api/ blocks
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

INCLUDE = "    include snippets/ailt-api-location.conf;"


def normalize(text: str) -> tuple[str, dict[str, int | bool]]:
    # Drop inline location /ailt/api/ { ... }
    text, n_inline = re.subn(
        r"^[ \t]*location[ \t]+/ailt/api/[ \t]*\{.*?\n^[ \t]*\}[ \t]*\n?",
        "",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    # Drop every existing snippet include (may be nested wrongly)
    text, n_inc = re.subn(
        r"^[ \t]*include[ \t]+snippets/ailt-api-location\.conf;[ \t]*\n?",
        "",
        text,
        flags=re.MULTILINE,
    )

    lines = text.splitlines()
    out: list[str] = []
    depth = 0
    inserted = False

    def is_catch_all_location(line: str) -> bool:
        # Exact "location / {" — not /api/, /static/, etc.
        return bool(re.match(r"^[ \t]*location[ \t]+/[ \t]*\{", line))

    for line in lines:
        # Server body is depth == 1
        if depth == 1 and is_catch_all_location(line) and not inserted:
            out.append(INCLUDE)
            inserted = True
        out.append(line)
        depth += line.count("{") - line.count("}")

    if not inserted:
        final: list[str] = []
        depth = 0
        for line in out:
            delta = line.count("{") - line.count("}")
            if depth == 1 and delta < 0 and not inserted:
                final.append(INCLUDE)
                inserted = True
            final.append(line)
            depth += delta
        out = final

    result = "\n".join(out)
    if not result.endswith("\n"):
        result += "\n"
    return result, {
        "removed_inline": n_inline,
        "removed_includes": n_inc,
        "inserted": inserted,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/nginx/site.conf", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1
    original = path.read_text(encoding="utf-8")
    new_text, stats = normalize(original)
    if new_text != original:
        path.write_text(new_text, encoding="utf-8")
    print(
        f"{path}: removed_inline={stats['removed_inline']} "
        f"removed_includes={stats['removed_includes']} "
        f"server_level_include={stats['inserted']}"
    )
    return 0 if stats["inserted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
