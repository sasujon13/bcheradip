#!/usr/bin/env python3
"""
Copy [IMG] ... cell content from CsvExport2 into CsvExport by matching rows (row counts may differ).

For each pair of CSV files with the same relative path under two roots:
  CsvExport2/<path>.csv  (source: may contain [IMG] markers from json_to_csv_with_images.py)
  CsvExport/<path>.csv   (target: updated in place when rows match)

CsvExport may have extra dummy rows vs CsvExport2; rows are not matched by index.

Matching uses **Excel columns E through Q only** (0-based indices 4–16: Topic … Subsources).
Columns A–D and after Q are ignored for matching.

For each data row in CsvExport2 that contains '[IMG]' in at least one cell **in E–Q**:
  - Find row(s) in CsvExport where, for every column in **E–Q**, if **either** row has '[IMG]' in
    that column, that column is ignored for matching; otherwise the two cells must be equal.
  - If exactly one CsvExport row matches, copy '[IMG]' cell values from CsvExport2 **in E–Q**
    into that CsvExport row.
  - If zero matches: skip (no unique target). If more than one match: skip (ambiguous).

Each CsvExport row is updated at most once (first matching CsvExport2 row wins).

Usage:
  python merge_csv_images_export2_into_export.py
  python merge_csv_images_export2_into_export.py --dry-run
  python merge_csv_images_export2_into_export.py --export D:\\a\\CsvExport --export2 D:\\a\\CsvExport2
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Tuple

IMG_MARKER = "[IMG]"

# Excel columns E..Q (inclusive): Topic through Subsources — only these participate in match & merge.
MATCH_COL_START = 4
MATCH_COL_END_INCLUSIVE = 16

# Edit these if your folders differ
DEFAULT_EXPORT_DIR = Path(r"D:\VSCode\database\CsvExport")
DEFAULT_EXPORT2_DIR = Path(r"D:\VSCode\database\CsvExport2")


def _raise_csv_field_limit() -> None:
    """Default csv limit is 128KiB per field; question cells with long [IMG] lines need more."""
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


def _pad_row(r: List[str], n: int) -> List[str]:
    out = list(r)
    while len(out) < n:
        out.append("")
    return out[:n]


def _row_has_img_in_export2(row2: List[str]) -> bool:
    """True if any cell in columns E–Q contains IMG_MARKER."""
    n = max(len(row2), MATCH_COL_END_INCLUSIVE + 1)
    r2 = _pad_row(row2, n)
    for j in range(MATCH_COL_START, MATCH_COL_END_INCLUSIVE + 1):
        if IMG_MARKER in (r2[j] or ""):
            return True
    return False


def _non_img_cells_match(row1: List[str], row2: List[str]) -> bool:
    """Within columns E–Q: skip columns where either row contains IMG_MARKER; else require equality."""
    n = max(len(row1), len(row2), MATCH_COL_END_INCLUSIVE + 1)
    r1 = _pad_row(row1, n)
    r2 = _pad_row(row2, n)
    for j in range(MATCH_COL_START, MATCH_COL_END_INCLUSIVE + 1):
        c1, c2 = (r1[j] or ""), (r2[j] or "")
        if IMG_MARKER in c1 or IMG_MARKER in c2:
            continue
        if c1 != c2:
            return False
    return True


def _merge_img_cells(row1: List[str], row2: List[str]) -> List[str]:
    """Copy [IMG] cells from row2 into row1 for columns E–Q only."""
    n = max(len(row1), len(row2), MATCH_COL_END_INCLUSIVE + 1)
    out = _pad_row(row1, n)
    r2 = _pad_row(row2, n)
    for j in range(MATCH_COL_START, MATCH_COL_END_INCLUSIVE + 1):
        if IMG_MARKER in (r2[j] or ""):
            out[j] = r2[j]
    return out


def _process_file_pair(
    path_export: Path,
    path_export2: Path,
    *,
    dry_run: bool,
) -> Tuple[int, int, int, str | None]:
    """
    Returns (rows_updated, no_unique_match, ambiguous, error_or_none).

    no_unique_match: CsvExport2 rows with [IMG] that matched zero CsvExport rows.
    ambiguous: CsvExport2 rows with [IMG] that matched more than one CsvExport row.
    """
    try:
        rows1 = _read_csv_rows(path_export)
        rows2 = _read_csv_rows(path_export2)
    except OSError as e:
        return 0, 0, 0, str(e)

    if not rows1:
        return 0, 0, 0, "empty CsvExport"
    if not rows2:
        return 0, 0, 0, "empty CsvExport2"

    header = rows1[0]
    out_data: List[List[str]] = [list(r) for r in rows1[1:]]
    n_export = len(out_data)

    updated = 0
    no_unique_match = 0
    ambiguous = 0
    used_export_idx: set[int] = set()

    for r2 in rows2[1:]:
        if not _row_has_img_in_export2(r2):
            continue

        candidates = [
            i
            for i in range(n_export)
            if i not in used_export_idx and _non_img_cells_match(out_data[i], r2)
        ]

        if len(candidates) == 0:
            no_unique_match += 1
            continue
        if len(candidates) > 1:
            ambiguous += 1
            continue

        idx = candidates[0]
        before = out_data[idx][:]
        merged = _merge_img_cells(out_data[idx], r2)
        if merged != before:
            updated += 1
        out_data[idx] = merged
        used_export_idx.add(idx)

    out_rows: List[List[str]] = [header] + out_data

    if not dry_run and updated > 0:
        _write_csv_rows(path_export, out_rows)

    return updated, no_unique_match, ambiguous, None


def _collect_csv_files(root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.csv") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge [IMG] cells from CsvExport2 CSVs into matching rows in CsvExport.",
    )
    ap.add_argument(
        "--export",
        type=Path,
        default=DEFAULT_EXPORT_DIR,
        help="Target root (updated in place). Default: %(default)s",
    )
    ap.add_argument(
        "--export2",
        type=Path,
        default=DEFAULT_EXPORT2_DIR,
        help="Source root with [IMG] text. Default: %(default)s",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing CsvExport files.",
    )
    args = ap.parse_args()

    root2 = args.export2.resolve()
    root1 = args.export.resolve()

    if not root2.is_dir():
        print("Not a directory:", root2, file=sys.stderr)
        return 1
    if not root1.is_dir():
        print("Not a directory:", root1, file=sys.stderr)
        return 1

    files2 = _collect_csv_files(root2)
    if not files2:
        print("No *.csv under", root2, file=sys.stderr)
        return 1

    total_updated = 0
    total_no_match = 0
    total_ambiguous = 0
    files_changed = 0
    errors: List[str] = []

    for f2 in files2:
        try:
            rel = f2.relative_to(root2)
        except ValueError:
            rel = Path(f2.name)
        f1 = root1 / rel

        if not f1.is_file():
            errors.append("missing in CsvExport: %s" % f1)
            continue

        u, nm, amb, err = _process_file_pair(f1, f2, dry_run=args.dry_run)
        if err:
            errors.append("%s: %s" % (rel, err))
            continue
        total_updated += u
        total_no_match += nm
        total_ambiguous += amb
        if u > 0:
            files_changed += 1
        if u > 0 or nm > 0 or amb > 0:
            print(
                "%s  ->  updated %d row(s), no_match %d, ambiguous %d"
                % (rel, u, nm, amb)
            )

    print(
        "Done. Files with updates: %d / %d pair(s). Rows updated: %d. "
        "[IMG] rows with no CsvExport match: %d. [IMG] rows ambiguous: %d.%s"
        % (
            files_changed,
            len(files2),
            total_updated,
            total_no_match,
            total_ambiguous,
            " (dry-run; no files written)" if args.dry_run else "",
        )
    )
    for e in errors:
        print("WARN:", e, file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
