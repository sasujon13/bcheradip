#!/usr/bin/env python3
"""
Rebuild scraper-style CSV from Daricomma JSON, embedding image URLs in Question / Answer / Explanation.

The backend helper _scraper_extract_text() only joins blocks[].text, so Draft.js IMAGE entities
(entityRanges + entityMap type IMAGE) never appear in CSV. This script inserts each image as:

  [IMG] https://...

Usage:
  python json_to_csv_with_images.py
      (no args: reads D:\\VSCode\\database\\Data, writes CSVs under D:\\VSCode\\database\\CsvExport)
  python json_to_csv_with_images.py path/to/questions.json
  python json_to_csv_with_images.py path/to/questions.json -o out.csv
  python json_to_csv_with_images.py path/to/questions.csv --img-format markdown
  python json_to_csv_with_images.py --data-dir D:\\VSCode\\database\\Data
  python json_to_csv_with_images.py --data-dir D:\\VSCode\\database\\Data --csv-out-dir D:\\export\\csv

  --data-dir: recursively read every *.json under all subfolders; write one .csv per .json
              (next to the JSON, or under --csv-out-dir with the same relative paths).

Input JSON: a list of question objects, or { "data": [...] }, or { "questions": [...] }.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# Defaults when running: python json_to_csv_with_images.py  (no arguments)
DEFAULT_DATA_ROOT = Path(r"D:\VSCode\database\Data")
DEFAULT_CSV_EXPORT_DIR = Path(r"D:\VSCode\database\CsvExport")
DEFAULT_AUTHOR = "Cheradip"

EditorJson = Dict[str, Any]


def _normalize_entity_map(entity_map: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(entity_map, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in entity_map.items():
        if isinstance(v, dict):
            out[str(k)] = v
    return out


def _entity_image_src(ent: Dict[str, Any]) -> str:
    if ent.get("type") != "IMAGE":
        return ""
    data = ent.get("data") or {}
    return (data.get("src") or "").strip()


def draftjs_to_text_with_images(editor_obj: Any, img_line_format: str = "tag") -> str:
    """
    Draft.js / legacy rich text: blocks + entityMap.
    img_line_format: 'tag' -> newline + [IMG] url + newline
                     'markdown' -> newline + ![](url) + newline
                     'url' -> url alone on its own line
    """
    if editor_obj is None:
        return ""
    if isinstance(editor_obj, str):
        return editor_obj
    if not isinstance(editor_obj, dict):
        return str(editor_obj)

    blocks = editor_obj.get("blocks") or []
    entity_map = _normalize_entity_map(editor_obj.get("entityMap"))

    def format_img(src: str) -> str:
        if not src:
            return ""
        if img_line_format == "markdown":
            return "\n![](%s)\n" % src
        if img_line_format == "url":
            return "\n%s\n" % src
        return "\n[IMG] %s\n" % src

    lines_out: List[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if text is None:
            text = ""
        else:
            text = str(text)
        ranges = list(block.get("entityRanges") or [])
        ranges.sort(key=lambda r: (int(r.get("offset", 0)), int(r.get("length", 0))))

        if not ranges:
            lines_out.append(text)
            continue

        parts: List[str] = []
        pos = 0
        for r in ranges:
            off = int(r.get("offset", 0))
            ln = int(r.get("length", 0))
            key = r.get("key")
            ent = entity_map.get(str(key)) if key is not None else None

            if off > pos:
                parts.append(text[pos:off])

            if isinstance(ent, dict):
                src = _entity_image_src(ent)
                if src:
                    parts.append(format_img(src))
                else:
                    parts.append(text[off : off + ln])
            else:
                parts.append(text[off : off + ln])
            pos = off + ln

        parts.append(text[pos:])
        lines_out.append("".join(parts))

    return "\n".join(lines_out).strip()


def _option_plain(opt: Any, img_line_format: str) -> str:
    if opt is None:
        return ""
    if isinstance(opt, str):
        return opt
    if isinstance(opt, dict) and ("blocks" in opt or "entityMap" in opt):
        return draftjs_to_text_with_images(opt, img_line_format)
    return str(opt)


def _load_questions(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("data", "questions", "items", "results"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    raise ValueError("JSON must be a list of questions or an object with data/questions/items/results array")


def _format_topics(q: Dict[str, Any]) -> str:
    topic_names: List[str] = []
    topics = q.get("topic")
    if isinstance(topics, list):
        for t in topics:
            if isinstance(t, dict) and t.get("name"):
                topic_names.append('"%s"' % t["name"])
    elif isinstance(topics, dict) and topics.get("name"):
        topic_names.append('"%s"' % topics["name"])
    return ", ".join(topic_names)


def _format_subsources(q: Dict[str, Any]) -> str:
    out: List[str] = []
    for sub in q.get("question_subsources") or []:
        if not isinstance(sub, dict):
            continue
        sub_source = sub.get("sub_source") or {}
        year_obj = sub.get("year") or {}
        short_name = sub_source.get("name", "")
        year_name = year_obj.get("name", "")
        if short_name and year_name:
            yy = year_name[-2:] if len(year_name) >= 2 else year_name
            out.append('"%s\'%s"' % (short_name, yy))
    return ", ".join(out)


def json_questions_to_csv_rows(
    questions: List[Dict[str, Any]],
    *,
    default_subject: str = "",
    img_line_format: str = "tag",
) -> List[List[Any]]:
    rows: List[List[Any]] = []
    for idx, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            continue
        level1 = q.get("_level1") or default_subject or ""
        chapter_no = q.get("_chapter_no", "") or ""
        chapter = q.get("_chapter", "") or ""
        options = q.get("option") or []
        correct_index = q.get("mcq_solution_index")
        correct_answer = ""
        if isinstance(correct_index, int) and 0 <= correct_index < len(options):
            correct_answer = _option_plain(options[correct_index], img_line_format)

        qtext = draftjs_to_text_with_images(q.get("question_text"), img_line_format)
        expl_raw = q.get("answer_text") or q.get("explanation_text")
        expl = draftjs_to_text_with_images(expl_raw, img_line_format)
        qtype = (q.get("question_type") or {}).get("name", "") if isinstance(q.get("question_type"), dict) else ""
        qlevel = (q.get("question_level") or {}).get("name", "") if isinstance(q.get("question_level"), dict) else ""

        opt_cells = [_option_plain(options[i], img_line_format) if i < len(options) else "" for i in range(4)]

        rows.append(
            [
                idx,
                level1,
                chapter_no,
                chapter,
                _format_topics(q),
                qtext,
                opt_cells[0],
                opt_cells[1],
                opt_cells[2],
                opt_cells[3],
                correct_answer,
                expl,
                "",
                "",
                qtype,
                qlevel,
                _format_subsources(q),
                "",
                "",
                DEFAULT_AUTHOR,
            ]
        )
    return rows


CSV_HEADER = [
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


def _collect_json_files(root: Path) -> List[Path]:
    """All *.json files under root (recursive), sorted for stable runs."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def _write_one_csv(
    inp: Path,
    out: Path,
    *,
    default_subject: str,
    img_line_format: str,
) -> tuple[int, Optional[str]]:
    """
    Returns (row_count, error_message). error_message set on failure (row_count 0).
    """
    try:
        questions = _load_questions(inp)
    except (json.JSONDecodeError, ValueError) as e:
        return 0, "%s: %s" % (inp, e)

    rows = json_questions_to_csv_rows(
        questions,
        default_subject=default_subject,
        img_line_format=img_line_format,
    )

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(CSV_HEADER)
            w.writerows(rows)
    except OSError as e:
        return 0, "%s -> %s: %s" % (inp, out, e)

    return len(rows), None


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convert Daricomma JSON to CSV with image URLs in text fields.",
        epilog="Example:  python json_to_csv_with_images.py C:\\path\\to\\questions.json\n"
        "          python json_to_csv_with_images.py questions.json -o out.csv --img-format markdown\n"
        "          python json_to_csv_with_images.py --data-dir D:\\\\VSCode\\\\database\\\\Data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "input_json",
        type=Path,
        nargs="?",
        help="Path to a single questions .json (list of objects, or wrapper with data/questions/items/results)",
    )
    p.add_argument(
        "--data-dir",
        type=Path,
        nargs="?",
        const=DEFAULT_DATA_ROOT,
        default=None,
        metavar="DIR",
        help="Recursively convert every *.json under DIR (default DIR: %(const)s). "
        "Writes one .csv per .json. Implies batch mode; do not pass input_json.",
    )
    p.add_argument(
        "--csv-out-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="With --data-dir: write CSVs under DIR, preserving relative paths from --data-dir. "
        "If omitted, each .csv is written next to its .json (unless you run with no args; then see DEFAULT_CSV_EXPORT_DIR in code).",
    )
    p.add_argument("-o", "--output", type=Path, help="Output .csv (single-file mode only; default: same basename as input)")
    p.add_argument(
        "--img-format",
        choices=("tag", "markdown", "url"),
        default="tag",
        help="How to embed images: [IMG] url, markdown image, or bare URL per line (default: tag)",
    )
    p.add_argument("--subject", default="", help="Default Subject if _level1 is missing")
    args = p.parse_args()

    data_dir = args.data_dir
    inp = args.input_json
    csv_out_dir = args.csv_out_dir

    # No CLI args except script name: use fixed data + export paths (edit DEFAULT_* in code if needed).
    if len(sys.argv) == 1:
        data_dir = DEFAULT_DATA_ROOT
        csv_out_dir = DEFAULT_CSV_EXPORT_DIR

    if data_dir is not None:
        if inp is not None:
            print("Use either a single input_json file OR --data-dir, not both.", file=sys.stderr)
            return 2
        if args.output is not None:
            print("-o/--output is not valid with --data-dir (each file gets its own .csv).", file=sys.stderr)
            return 2
        if not data_dir.is_dir():
            print("Directory not found:", data_dir, file=sys.stderr)
            return 1

        json_files = _collect_json_files(data_dir)
        if not json_files:
            print("No *.json files under", data_dir, file=sys.stderr)
            return 1

        total_rows = 0
        errors: List[str] = []
        for jf in json_files:
            if csv_out_dir is not None:
                try:
                    rel = jf.relative_to(data_dir.resolve())
                except ValueError:
                    rel = Path(jf.name)
                out = (csv_out_dir / rel).with_suffix(".csv")
            else:
                out = jf.with_suffix(".csv")

            n, err = _write_one_csv(
                jf,
                out,
                default_subject=args.subject,
                img_line_format=args.img_format,
            )
            if err:
                errors.append(err)
            else:
                total_rows += n
                print("Wrote %d rows -> %s" % (n, out))

        print(
            "Done: %d JSON file(s), %d total data rows, %d error(s)."
            % (len(json_files), total_rows, len(errors)),
        )
        for e in errors:
            print("SKIP:", e, file=sys.stderr)
        return 1 if errors else 0

    if inp is None:
        p.print_help()
        print(
            "\nMissing input: pass one JSON file, or use batch mode:\n"
            "  python json_to_csv_with_images.py path\\to\\your_questions.json\n"
            "  python json_to_csv_with_images.py --data-dir\n"
            "  python json_to_csv_with_images.py --data-dir D:\\VSCode\\database\\Data",
            file=sys.stderr,
        )
        return 2
    if not inp.is_file():
        print("File not found:", inp, file=sys.stderr)
        return 1

    out = args.output
    if out is None:
        out = inp.with_suffix(".csv")

    n, err = _write_one_csv(
        inp,
        out,
        default_subject=args.subject,
        img_line_format=args.img_format,
    )
    if err:
        print("Failed:", err, file=sys.stderr)
        return 1

    print("Wrote %d rows -> %s" % (n, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
