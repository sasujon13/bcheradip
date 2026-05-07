#!/usr/bin/env python3
"""
Parse phpMyAdmin-style INSERT INTO table (cols) VALUES (row1), (row2), ...
from stdin or file and output CSV. Handles NULL, numbers, and 'string' (with '' escaped).
"""
import re
import sys
import csv


def parse_value(s):
    """Parse one value from start of s; return (value, rest). Value is str or None for NULL."""
    s = s.lstrip()
    if s.startswith("NULL"):
        return ("", s[4:].lstrip().lstrip(",").lstrip())
    if s.startswith("'"):
        # find matching quote ('' is escaped)
        i = 1
        while i < len(s):
            if s[i : i + 2] == "''":
                i += 2
                continue
            if s[i] == "'":
                break
            i += 1
        inner = s[1:i].replace("''", "'")
        return (inner, s[i + 1 :].lstrip().lstrip(",").lstrip())
    m = re.match(r"-?\d+(?:\.\d+)?", s)
    if m:
        return (m.group(0), s[m.end() :].lstrip().lstrip(",").lstrip())
    return ("", s.lstrip(",").lstrip())


def parse_row(row_str):
    """Parse one (...) row string into list of values."""
    row_str = row_str.strip().strip("()").strip()
    values = []
    while row_str:
        val, row_str = parse_value(row_str)
        values.append(val)
    return values


def extract_inserts(text):
    """Extract (columns, list of row value lists) from one or more INSERT statements."""
    # INSERT INTO `table` (col1, col2, ...) VALUES (row1), (row2);
    pattern = re.compile(
        r"INSERT\s+INTO\s+`(\w+)`\s*\(([^)]+)\)\s+VALUES\s*(.+)",
        re.IGNORECASE | re.DOTALL,
    )
    cols = None
    rows = []
    for m in pattern.finditer(text):
        table = m.group(1)
        col_str = m.group(2)
        vals_block = m.group(3).strip()
        if cols is None:
            cols = [c.strip().strip("`").strip() for c in col_str.split(",")]
        # Split into row strings: (a,b,c), (d,e,f) -> ["a,b,c", "d,e,f"]
        row_strs = re.split(r\)\s*,\s*\(", vals_block)
        for i, rs in enumerate(row_strs):
            rs = rs.strip()
            if not rs or rs.startswith("--") or rs.startswith("/*"):
                continue
            if not rs.startswith("("):
                rs = "(" + rs
            if not rs.rstrip().endswith(")"):
                rs = rs + ")"
            rs = re.sub(r\)\s*;.*$", ")", rs, flags=re.DOTALL)
            row = parse_row(rs)
            if len(row) == len(cols):
                rows.append(row)
    return cols, rows


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    cols, rows = extract_inserts(text)
    if not cols:
        print("No INSERT statements found.", file=sys.stderr)
        sys.exit(1)

    out = sys.stdout
    if len(sys.argv) > 2:
        out = open(sys.argv[2], "w", encoding="utf-8", newline="")

    writer = csv.writer(out)
    writer.writerow(cols)
    for row in rows:
        writer.writerow(row)

    if out is not sys.stdout:
        out.close()
    print("Rows written: %d" % len(rows), file=sys.stderr)


if __name__ == "__main__":
    main()
