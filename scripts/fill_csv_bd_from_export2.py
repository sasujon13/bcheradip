#!/usr/bin/env python3
"""
Fill Excel columns B–D (Subject, ChapterNo, Chapter) in CsvExport from CsvExport2.

For each pair of CSV files with the same relative path under two roots:
  CsvExport2/<path>.csv  (source: B–D and E–Q)
  CsvExport/<path>.csv   (target: B–D updated in place; E–Q used for matching)

Matching uses **Excel columns E through Q only** (0-based indices 4–16: Topic … Subsources).
A–D and columns after Q are ignored for matching.

Within E–Q, any column where **either** row contains the ``[IMG]`` marker is **not** compared; remaining
columns must match exactly (pairwise).

For each **data row** in CsvExport (same order as the file):
  - If some row in CsvExport2 **matches** on E–Q under the rule above, copy B–D
    from the **first** such CsvExport2 row.
  - Otherwise, copy B–D from the **previous data row** in CsvExport2 (row index i−1 when
    the current CsvExport row is index i). For the first data row (i = 0) with no match,
    B–D are left empty. If i > 0 but row i−1 does not exist in CsvExport2 (shorter file),
    B–D are left empty.

Usage:
  python fill_csv_bd_from_export2.py
  python fill_csv_bd_from_export2.py --dry-run
  python fill_csv_bd_from_export2.py --export D:\\a\\CsvExport --export2 D:\\a\\CsvExport2
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Tuple

IMG_MARKER = "[IMG]"

# Excel columns E..Q (inclusive): Topic through Subsources.
MATCH_COL_START = 4
MATCH_COL_END_INCLUSIVE = 16

# Excel B..D (inclusive): Subject, ChapterNo, Chapter.
BD_COL_START = 1
BD_COL_END_INCLUSIVE = 3

DEFAULT_EXPORT_DIR = Path(r"D:\VSCode\database\CsvExport")
DEFAULT_EXPORT2_DIR = Path(r"D:\VSCode\database\CsvExport2")


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


def _pad_row(r: List[str], n: int) -> List[str]:
    out = list(r)
    while len(out) < n:
        out.append("")
    return out[:n]


def _eq_range(r1: List[str], r2: List[str]) -> bool:
    """E–Q match: columns where either side has [IMG] are skipped; others must be equal."""
    n = max(len(r1), len(r2), MATCH_COL_END_INCLUSIVE + 1)
    a = _pad_row(r1, n)
    b = _pad_row(r2, n)
    for j in range(MATCH_COL_START, MATCH_COL_END_INCLUSIVE + 1):
        ca, cb = (a[j] or ""), (b[j] or "")
        if IMG_MARKER in ca or IMG_MARKER in cb:
            continue
        if ca != cb:
            return False
    return True


def _apply_bd(dst: List[str], src: List[str]) -> None:
    while len(dst) < BD_COL_END_INCLUSIVE + 1:
        dst.append("")
    for j in range(BD_COL_START, BD_COL_END_INCLUSIVE + 1):
        dst[j] = src[j] if j < len(src) else ""


def _process_file_pair(
    path_export: Path,
    path_export2: Path,
    *,
    dry_run: bool,
) -> Tuple[int, int, int, int, str | None]:
    """
    Returns (rows_bd_changed, filled_by_match, filled_by_prior, skipped_empty, error_or_none).
    """
    try:
        rows1 = _read_csv_rows(path_export)
        rows2 = _read_csv_rows(path_export2)
    except OSError as e:
        return 0, 0, 0, 0, str(e)

    if not rows1:
        return 0, 0, 0, 0, "empty CsvExport"
    if not rows2:
        return 0, 0, 0, 0, "empty CsvExport2"

    header = rows1[0]
    out_data: List[List[str]] = [list(r) for r in rows1[1:]]
    data2 = [list(r) for r in rows2[1:]]
    n_export = len(out_data)
    n2 = len(data2)

    filled_match = 0
    filled_prior = 0
    skipped = 0
    changed = 0

    for i in range(n_export):
        r1 = out_data[i]
        j_match: int | None = None
        for j in range(n2):
            if _eq_range(r1, data2[j]):
                j_match = j
                break

        before = tuple(
            _pad_row(list(r1), BD_COL_END_INCLUSIVE + 1)[BD_COL_START : BD_COL_END_INCLUSIVE + 1]
        )

        if j_match is not None:
            _apply_bd(out_data[i], data2[j_match])
            filled_match += 1
        else:
            if i > 0 and (i - 1) < n2:
                _apply_bd(out_data[i], data2[i - 1])
                filled_prior += 1
            else:
                skipped += 1
                # Leave B–D as-is (typically empty)
                continue

        after = tuple(
            _pad_row(list(out_data[i]), BD_COL_END_INCLUSIVE + 1)[
                BD_COL_START : BD_COL_END_INCLUSIVE + 1
            ]
        )
        if after != before:
            changed += 1

    out_rows: List[List[str]] = [header] + out_data

    if not dry_run and changed > 0:
        _write_csv_rows(path_export, out_rows)

    return changed, filled_match, filled_prior, skipped, None


def _collect_csv_files(root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.csv") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fill Subject/ChapterNo/Chapter (B–D) in CsvExport from CsvExport2 by E–Q match or prior row.",
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
        help="Source root. Default: %(default)s",
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

    total_changed = 0
    total_match = 0
    total_prior = 0
    total_skipped = 0
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

        ch, m, p, sk, err = _process_file_pair(f1, f2, dry_run=args.dry_run)
        if err:
            errors.append("%s: %s" % (rel, err))
            continue
        total_changed += ch
        total_match += m
        total_prior += p
        total_skipped += sk
        if ch > 0:
            files_changed += 1
        if ch > 0 or m > 0 or p > 0 or sk > 0:
            print(
                "%s  ->  rows B–D changed: %d (match %d, prior_row %d, skipped_no_fill %d)"
                % (rel, ch, m, p, sk)
            )

    print(
        "Done. Files with B–D changes: %d / %d pair(s). Rows with B–D changed: %d. "
        "Filled by E–Q match: %d. Filled by prior CsvExport2 row: %d. No fill: %d.%s"
        % (
            files_changed,
            len(files2),
            total_changed,
            total_match,
            total_prior,
            total_skipped,
            " (dry-run; no files written)" if args.dry_run else "",
        )
    )
    for e in errors:
        print("WARN:", e, file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
