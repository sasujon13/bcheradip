#!/usr/bin/env python3
"""
Rewrite every *.csv under a root so columns match the Cheradip export schema:

  ... Answer | Explanation | Explanation2 | Explanation3 | Question Type | Level |
  Subsources | (empty) | (empty) | Author

- Explanation2 / Explanation3: empty if missing in source.
- Two unnamed columns after Subsources: always empty.
- Author: default \"Cheradip\" when missing or blank.

- ChapterNo (column C): strip leading \"অধ্যায়-\" and trailing \":\" (e.g. \"অধ্যায়-০১:\" → \"০১\").

- Level: remove any prefix before the first \":\" (e.g. \"MCQ: All Levels\" → \"All Levels\").

Existing columns are matched by header name (case-insensitive); extra source columns are dropped.
Same order as json_to_csv_with_images.py CSV_HEADER.

Usage:
  python csv_normalize_explanation2_author.py
  python csv_normalize_explanation2_author.py --dry-run
  python csv_normalize_explanation2_author.py --root D:\\VSCode\\database\\CsvExport
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Must match json_to_csv_with_images.py CSV_HEADER
TARGET_HEADER: List[str] = [
    "ID",
    "Subject",
    "ChapterNo",
    "Chapter",
    "Topic",
    "Question",
    "Option 1",
    "Option 2",
    "Option 3",
    "Option 4",
    "Answer",
    "Explanation",
    "Explanation2",
    "Explanation3",
    "Question Type",
    "Level",
    "Subsources",
    "",
    "",
    "Author",
]

DEFAULT_ROOT = Path(r"D:\VSCode\database\CsvExport2")
DEFAULT_AUTHOR = "Cheradip"

# Bengali \"chapter\" prefix in some exports, e.g. অধ্যায়-০১:
CHAPTER_NO_PREFIX = "অধ্যায়-"


def _raise_csv_field_limit() -> None:
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(2**31 - 1)


_raise_csv_field_limit()


def _log(msg: str) -> None:
    print("[csv_normalize] %s" % msg, flush=True)


def clean_chapter_no(value: str) -> str:
    """
    Column ChapterNo: remove leading 'অধ্যায়-' and trailing ':' (and trim).
    Example: 'অধ্যায়-০১:' -> '০১'
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.startswith(CHAPTER_NO_PREFIX):
        s = s[len(CHAPTER_NO_PREFIX) :].strip()
    s = s.rstrip(":").strip()
    return s


def clean_level(value: str) -> str:
    """
    Column Level: keep only the part after the first ':' (trimmed).
    Example: 'MCQ: All Levels' -> 'All Levels', 'CQ: Easy' -> 'Easy'.
    Values without ':' are unchanged.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    return s


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


def _canonical_named_header(cell: str) -> Optional[str]:
    """
    Map a source header cell to one of TARGET_HEADER named columns (not the two '' slots).
    Returns None if unknown.
    """
    raw = (cell or "").strip()
    if not raw:
        return None
    k = raw.lower()
    aliases: Dict[str, str] = {
        "subsource": "Subsources",
    }
    if k in aliases:
        return aliases[k]
    for t in TARGET_HEADER:
        if t and t.lower() == k:
            return t
    return None


def _values_by_canonical(header: List[str], row: List[str]) -> Dict[str, str]:
    """First occurrence wins for each canonical column name."""
    out: Dict[str, str] = {}
    n = max(len(header), len(row))
    h = header + [""] * (n - len(header))
    r = row + [""] * (n - len(row))
    for i in range(n):
        c = _canonical_named_header(h[i])
        if c and c not in out:
            out[c] = r[i]
    return out


def _build_target_row(by_name: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for t in TARGET_HEADER:
        if t == "":
            out.append("")
            continue
        v = by_name.get(t, "")
        if t == "ChapterNo":
            v = clean_chapter_no(v if isinstance(v, str) else ("" if v is None else str(v)))
        if t == "Level":
            v = clean_level(v if isinstance(v, str) else ("" if v is None else str(v)))
        if t == "Author" and not (v or "").strip():
            v = DEFAULT_AUTHOR
        out.append(v)
    return out


def _process_file(path: Path, *, dry_run: bool) -> tuple[bool, Optional[str]]:
    """
    Returns (changed, error_message).
    """
    _log("step 1: open/read -> %s" % path)
    try:
        rows = _read_csv_rows(path)
    except OSError as e:
        _log("FAIL: read error: %s" % e)
        return False, str(e)
    if not rows:
        _log("FAIL: empty file (no rows)")
        return False, "empty file"

    _log("step 2: read OK, %d line(s) (incl. header)" % len(rows))
    header_in = rows[0]
    _log("step 3: source header cells: %d" % len(header_in))

    new_rows: List[List[str]] = [list(TARGET_HEADER)]
    chapter_cleaned = 0
    level_cleaned = 0
    for i, data in enumerate(rows[1:], start=1):
        try:
            by_name = _values_by_canonical(header_in, data)
            raw_cn = by_name.get("ChapterNo", "") or ""
            raw_s = raw_cn if isinstance(raw_cn, str) else str(raw_cn)
            if raw_s.strip() != clean_chapter_no(raw_s):
                chapter_cleaned += 1
            raw_lv = by_name.get("Level", "") or ""
            raw_l = raw_lv if isinstance(raw_lv, str) else str(raw_lv)
            if raw_l.strip() != clean_level(raw_l):
                level_cleaned += 1
            new_rows.append(_build_target_row(by_name))
        except Exception as e:
            _log("FAIL: row %d: %s" % (i, e))
            return False, "row %d: %s" % (i, e)

    _log(
        "step 4: built %d data row(s); ChapterNo normalized in %d row(s); Level normalized in %d row(s)"
        % (len(rows) - 1, chapter_cleaned, level_cleaned)
    )
    _log("step 5: compare old vs new (full row lists)")

    if len(rows) == len(new_rows) and rows == new_rows:
        _log("step 6: no changes needed (skip write)")
        return False, None

    _log("step 6: content differs -> will %s" % ("dry-run only" if dry_run else "write file"))
    if not dry_run:
        try:
            _write_csv_rows(path, new_rows)
        except OSError as e:
            _log("FAIL: write error: %s" % e)
            return False, str(e)
        _log("step 7: write OK -> %s" % path)
    else:
        _log("step 7: dry-run, no write")

    return True, None


def _collect_csv_files(root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.csv") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Normalize CSV columns (Explanation2/3, ChapterNo, Level prefix strip, Author=Cheradip).",
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Root folder to scan for *.csv. Default: %(default)s",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which files would change without writing.",
    )
    args = ap.parse_args()

    _log("start: argv dry_run=%s root=%s" % (args.dry_run, args.root))
    root = args.root.resolve()
    _log("resolved root: %s" % root)
    if not root.is_dir():
        _log("FAIL: root is not a directory")
        print("Not a directory:", root, file=sys.stderr)
        return 1

    files = _collect_csv_files(root)
    _log("discovered %d CSV file(s) under root (recursive rglob)" % len(files))
    if not files:
        _log("FAIL: no *.csv files")
        print("No *.csv under", root, file=sys.stderr)
        return 1

    changed = 0
    errors: List[str] = []
    for n, f in enumerate(files, start=1):
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = Path(f.name)
        _log("--- file %d/%d: %s ---" % (n, len(files), rel))
        ch, err = _process_file(f, dry_run=args.dry_run)
        if err:
            errors.append("%s: %s" % (rel, err))
            _log("file result: ERROR (see above)")
            continue
        if ch:
            changed += 1
            print("updated:", rel)
            _log("file result: updated")
        else:
            _log("file result: unchanged")

    print(
        "Done. Files %s: %d / %d.%s"
        % (
            "that would change" if args.dry_run else "updated",
            changed,
            len(files),
            " (dry-run; no writes)" if args.dry_run else "",
        )
    )
    _log("summary: changed=%d errors=%d dry_run=%s" % (changed, len(errors), args.dry_run))
    for e in errors:
        print("WARN:", e, file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
