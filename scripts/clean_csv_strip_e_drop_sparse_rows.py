#!/usr/bin/env python3
"""
Clean Cheradip export CSVs under CsvExport and CsvExport2.

For every ``*.csv`` under each root (recursive):

1. **Column E (Topic):** remove every literal double-quote character (``"``) from that cell
   in every row (header + data).

2. **Drop sparse data rows:** remove rows where **exactly three** columns are non-empty
   (after strip) and those three are **ID**, **Author**, and **one other** column — i.e. the
   only populated columns are ID, Author, and a single additional column (any other index).

Column positions are resolved from the header row (names ``ID``, ``Topic``, ``Author``);
defaults match ``json_to_csv_with_images.py`` (Topic index 4, Author last).

Usage:
  python clean_csv_strip_e_drop_sparse_rows.py
  python clean_csv_strip_e_drop_sparse_rows.py --dry-run
  python clean_csv_strip_e_drop_sparse_rows.py --export D:\\a\\CsvExport --export2 D:\\a\\CsvExport2
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Tuple

DEFAULT_EXPORT_DIR = Path(r"D:\VSCode\database\CsvExport")
DEFAULT_EXPORT2_DIR = Path(r"D:\VSCode\database\CsvExport2")

# Fallback indices if header names are missing (same as json_to_csv_with_images CSV_HEADER).
DEFAULT_ID_INDEX = 0
DEFAULT_TOPIC_INDEX = 4
DEFAULT_AUTHOR_INDEX = 19


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


def _find_header_index(header: List[str], name: str, default: int) -> int:
    h = [str(x).strip() for x in header]
    name_l = name.lower()
    for i, cell in enumerate(h):
        if cell.lower() == name_l:
            return i
    return default


def _resolve_indices(header: List[str]) -> Tuple[int, int, int]:
    """Return (id_index, topic_index, author_index)."""
    id_i = _find_header_index(header, "ID", DEFAULT_ID_INDEX)
    topic_i = _find_header_index(header, "Topic", DEFAULT_TOPIC_INDEX)
    auth_i = _find_header_index(header, "Author", DEFAULT_AUTHOR_INDEX)
    return id_i, topic_i, auth_i


def _strip_double_quotes_topic(rows: List[List[str]], topic_idx: int) -> int:
    """Remove every ``"`` from the Topic column. Mutates rows in place."""
    n_changed = 0
    for r in rows:
        while len(r) <= topic_idx:
            r.append("")
        before = r[topic_idx]
        after = before.replace('"', "")
        if after != before:
            r[topic_idx] = after
            n_changed += 1
    return n_changed


def _non_empty_indices(row: List[str], width: int) -> List[int]:
    p = _pad_row(row, width)
    return [i for i in range(width) if (p[i] or "").strip() != ""]


def _is_sparse_id_author_plus_one(
    row: List[str],
    width: int,
    id_idx: int,
    author_idx: int,
) -> bool:
    """
    True if exactly three columns are non-empty and they are ID, Author, and one other column.
    """
    if id_idx == author_idx:
        return False
    idxs = _non_empty_indices(row, width)
    if len(idxs) != 3:
        return False
    if id_idx not in idxs or author_idx not in idxs:
        return False
    return True


def _process_file(path: Path, *, dry_run: bool) -> Tuple[int, int, int, str | None]:
    """
    Returns (e_cells_changed, rows_removed, rows_out, error_or_none).
    rows_out is data row count after filtering.
    """
    try:
        rows = _read_csv_rows(path)
    except OSError as e:
        return 0, 0, 0, str(e)

    if not rows:
        return 0, 0, 0, "empty file"

    header = rows[0]
    id_idx, topic_idx, author_idx = _resolve_indices(header)
    width = len(header)
    for r in rows[1:]:
        width = max(width, len(r))
    width = max(width, id_idx + 1, topic_idx + 1, author_idx + 1, DEFAULT_AUTHOR_INDEX + 1)

    e_changed = _strip_double_quotes_topic(rows, topic_idx)

    data_in = rows[1:]
    kept: List[List[str]] = []
    removed = 0
    for row in data_in:
        if _is_sparse_id_author_plus_one(row, width, id_idx, author_idx):
            removed += 1
        else:
            kept.append(row)

    out_rows = [header] + kept

    if not dry_run and (e_changed > 0 or removed > 0):
        _write_csv_rows(path, out_rows)

    return e_changed, removed, len(kept), None


def _collect_csv_files(root: Path) -> List[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.csv") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Strip quotes from Topic (E) and drop rows with only ID+Author+one column filled.",
    )
    ap.add_argument(
        "--export",
        type=Path,
        default=DEFAULT_EXPORT_DIR,
        help="First root (updated in place). Default: %(default)s",
    )
    ap.add_argument(
        "--export2",
        type=Path,
        default=DEFAULT_EXPORT2_DIR,
        help="Second root (updated in place). Default: %(default)s",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing CSV files.",
    )
    args = ap.parse_args()

    roots = [args.export.resolve(), args.export2.resolve()]
    for root in roots:
        if not root.is_dir():
            print("Not a directory:", root, file=sys.stderr)
            return 1

    total_e = 0
    total_removed = 0
    files_touched = 0
    files_seen = 0

    for root in roots:
        label = root.name
        for f in _collect_csv_files(root):
            files_seen += 1
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = Path(f.name)
            e_ch, rem, n_out, err = _process_file(f, dry_run=args.dry_run)
            if err:
                print("WARN %s / %s: %s" % (label, rel, err), file=sys.stderr)
                continue
            if e_ch > 0 or rem > 0:
                files_touched += 1
                print(
                    "%s / %s  ->  Topic quotes stripped: %d cell(s); sparse rows removed: %d; "
                    "data rows left: %d"
                    % (label, rel, e_ch, rem, n_out)
                )
            total_e += e_ch
            total_removed += rem

    print(
        "Done. Files scanned: %d. Files with changes: %d. "
        "Total Topic cells stripped: %d. Total sparse rows removed: %d.%s"
        % (
            files_seen,
            files_touched,
            total_e,
            total_removed,
            " (dry-run; no files written)" if args.dry_run else "",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
