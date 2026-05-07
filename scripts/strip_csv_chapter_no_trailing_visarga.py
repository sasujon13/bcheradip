#!/usr/bin/env python3
"""
Rewrite every ``*.csv`` under a root (default: CsvExport) so **Subject** (column B) and
**ChapterNo** (column C) are normalized.

**Subject (column B):** drop everything before the **first** ASCII ``-`` and trim
(e.g. ``HSC - ব্যবসায় …`` → ``ব্যবসায় …``). Rows with no ``-`` are unchanged.

**ChapterNo (column C):**

- Remove leading **অধ্যায়-** / **অধ্যায়-** (chapter label), e.g. ``অধ্যায়-০১`` → ``০১``
  (same idea as ``csv_normalize_explanation2_author.clean_chapter_no``).
- Remove leading **Unit-** (case-insensitive), e.g. ``Unit-01`` → ``01``.
- Remove trailing **Bengali visarga** ``ঃ`` and trailing ASCII ``:``.

Columns are found by header names ``Subject`` and ``ChapterNo`` when present; otherwise
indices **1** (B) and **2** (C).

Usage:
  python strip_csv_chapter_no_trailing_visarga.py
  python strip_csv_chapter_no_trailing_visarga.py --dry-run
  python strip_csv_chapter_no_trailing_visarga.py --export D:\\VSCode\\database\\CsvExport
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List

DEFAULT_EXPORT_DIR = Path(r"D:\VSCode\database\CsvExport")
# Fallback 0-based indices when header names are missing (Excel B / C).
DEFAULT_SUBJECT_INDEX = 1
DEFAULT_CHAPTER_NO_INDEX = 2

# Bengali "chapter" prefix in exports (see csv_normalize_explanation2_author.CHAPTER_NO_PREFIX).
# Include common spelling variants (য় vsয়).
CHAPTER_NO_PREFIXES = (
    "অধ্যায়-",
    "অধ্যায়-",
)


def _raise_csv_field_limit() -> None:
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(2**31 - 1)


_raise_csv_field_limit()


def _read_csv_rows(path: Path) -> List[List[str]]:
    raw = path.read_text(encoding="utf-8-sig")
    rows: List[List[str]] = []
    for row in csv.reader(raw.splitlines()):
        rows.append([("" if c is None else str(c)) for c in row])
    return rows


def _write_csv_rows(path: Path, rows: List[List[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)


def _subject_index(header: List[str]) -> int:
    for i, h in enumerate(header):
        if str(h).strip().lower() == "subject":
            return i
    return DEFAULT_SUBJECT_INDEX


def _chapter_no_index(header: List[str]) -> int:
    for i, h in enumerate(header):
        if str(h).strip().lower() == "chapterno":
            return i
    return DEFAULT_CHAPTER_NO_INDEX


UNIT_PREFIX = "unit-"


def _normalize_subject_cell(value: str) -> str:
    """Keep only text after the first '-'. Trim (e.g. HSC - Title -> Title)."""
    s = str(value).strip()
    if not s or "-" not in s:
        return s
    return s.split("-", 1)[1].strip()


def _normalize_chapter_no_cell(value: str) -> str:
    """Strip অধ্যায়-/Unit-; remove trailing ঃ / : (e.g. অধ্যায়-০১ -> ০১, Unit-01 -> 01)."""
    s = str(value).strip()
    if not s:
        return ""
    # Leading অধ্যায়- (try longest / all variants)
    for prefix in sorted(CHAPTER_NO_PREFIXES, key=len, reverse=True):
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
            break
    # Leading "Unit-" (case-insensitive), ASCII hyphen only
    if s.lower().startswith(UNIT_PREFIX):
        s = s[len(UNIT_PREFIX) :].strip()
    # Trailing Bengali visarga and/or ASCII colon
    while True:
        t = s.rstrip()
        if t.endswith("ঃ"):
            s = t[:-1].strip()
            continue
        if t.endswith(":"):
            s = t[:-1].strip()
            continue
        break
    return s


def _process_file(path: Path, *, dry_run: bool) -> tuple[int, int, str | None]:
    """Returns (subject_cells_changed, chapter_no_cells_changed, error_or_none)."""
    try:
        rows = _read_csv_rows(path)
    except OSError as e:
        return 0, 0, str(e)

    if not rows:
        return 0, 0, None

    idx_s = _subject_index(rows[0])
    idx_c = _chapter_no_index(rows[0])
    changed_s = 0
    changed_c = 0

    for r in rows:
        while len(r) <= max(idx_s, idx_c):
            r.append("")

        before_s = r[idx_s]
        after_s = _normalize_subject_cell(before_s)
        if after_s != before_s:
            r[idx_s] = after_s
            changed_s += 1

        before_c = r[idx_c]
        after_c = _normalize_chapter_no_cell(before_c)
        if after_c != before_c:
            r[idx_c] = after_c
            changed_c += 1

    total = changed_s + changed_c
    if not dry_run and total > 0:
        _write_csv_rows(path, rows)

    return changed_s, changed_c, None


def _collect_csv_files(root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.csv") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Normalize Subject (B) and ChapterNo (C): strip before first '-'; অধ্যায়-/Unit-; trailing ঃ/:.",
    )
    ap.add_argument(
        "--export",
        type=Path,
        default=DEFAULT_EXPORT_DIR,
        help="Root directory (recursive *.csv). Default: %(default)s",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing files.",
    )
    args = ap.parse_args()

    root = args.export.resolve()
    if not root.is_dir():
        print("Not a directory:", root, file=sys.stderr)
        return 1

    files = _collect_csv_files(root)
    if not files:
        print("No *.csv under", root, file=sys.stderr)
        return 1

    total_subject = 0
    total_chapter = 0
    files_changed = 0
    errors: List[str] = []

    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = Path(f.name)
        ns, nc, err = _process_file(f, dry_run=args.dry_run)
        if err:
            errors.append("%s: %s" % (rel, err))
            continue
        if ns > 0 or nc > 0:
            files_changed += 1
            total_subject += ns
            total_chapter += nc
            print(
                "%s  ->  Subject cells: %d, ChapterNo cells: %d"
                % (rel, ns, nc)
            )

    print(
        "Done. Files with edits: %d / %d. Subject cells updated: %d. ChapterNo cells updated: %d.%s"
        % (
            files_changed,
            len(files),
            total_subject,
            total_chapter,
            " (dry-run; no files written)" if args.dry_run else "",
        )
    )
    for e in errors:
        print("WARN:", e, file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
