"""
Download http(s) assets referenced in string columns into MEDIA_ROOT/<db>/<table>/,
rename by qid, UPDATE rows on success; log failures with qid.

Usage:
  python manage.py download_media_from_db_urls
  python manage.py download_media_from_db_urls --dry-run
  python manage.py download_media_from_db_urls --database hsc
  python manage.py download_media_from_db_urls --table cheradip_alim_11_12_al_fiqh_1st_paper
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections

# Match http(s) URLs; trim common trailing punctuation from captures.
URL_RE = re.compile(r"https?://[^\s<\"\'\)\]\}]+", re.IGNORECASE)

TEXT_TYPES = frozenset(
    {"varchar", "char", "text", "tinytext", "mediumtext", "longtext"}
)

RETRIES = 3
TIMEOUT = 120
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _trim_url(url: str) -> str:
    u = url.rstrip()
    trim_chars = set(".,;:!?)'\"\\") | {"]"}
    while u and u[-1] in trim_chars:
        u = u[:-1]
    return u


def _find_urls(text: str) -> List[str]:
    if not text or "http" not in text.lower():
        return []
    seen: Set[str] = set()
    out: List[str] = []
    for m in URL_RE.finditer(text):
        u = _trim_url(m.group(0))
        if u.startswith("http://") or u.startswith("https://"):
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def _safe_fs_segment(name: str) -> str:
    bad = '<>:"/\\|?*'
    s = "".join(c if c not in bad else "_" for c in (name or ""))
    return s.strip() or "unnamed"


def _guess_ext(url: str, content_type: Optional[str]) -> str:
    path = urlparse(url).path
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico"):
        if path.lower().endswith(ext):
            return ext
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapping = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
            "application/pdf": ".pdf",
        }
        if ct in mapping:
            return mapping[ct]
    return ".bin"


def _download_once(url: str, dest_without_ext: Path, timeout: int) -> Tuple[bool, str]:
    """Write to dest_without_ext + guessed extension. Returns (ok, final path string)."""
    dest_without_ext.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(
            url,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        ) as r:
            r.raise_for_status()
            ext = _guess_ext(url, r.headers.get("Content-Type"))
            final = dest_without_ext.with_suffix(ext)
            with open(final, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if chunk:
                        f.write(chunk)
        return True, str(final)
    except Exception as e:
        return False, str(e)


def download_with_retries(url: str, dest: Path, timeout: int, retries: int) -> Tuple[bool, str]:
    last_err = ""
    for attempt in range(retries):
        ok, msg = _download_once(url, dest, timeout)
        if ok:
            return True, msg
        last_err = msg
        if attempt < retries - 1:
            time.sleep(min(8.0, 2.0**attempt))
    return False, last_err


def _relative_media_url(fs_path: Path, media_root: Path) -> str:
    """Web path under MEDIA_URL (e.g. /media/db/table/file.jpg)."""
    try:
        rel = fs_path.resolve().relative_to(media_root.resolve())
    except ValueError:
        rel = fs_path.name
    parts = [p.replace("\\", "/") for p in rel.parts]
    rel_s = "/".join(parts)
    base = (getattr(settings, "MEDIA_URL", "/media/") or "/media/").rstrip("/")
    return f"{base}/{rel_s}"


class Command(BaseCommand):
    help = (
        "Scan configured databases for tables with a qid column; find http(s) URLs in text columns; "
        "download to media/<db>/<table>/; UPDATE cells on success; log failures."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List work only; do not download or UPDATE.",
        )
        parser.add_argument(
            "--database",
            type=str,
            default=None,
            help="Process only this DB alias (e.g. hsc, default, honours, job).",
        )
        parser.add_argument(
            "--table",
            type=str,
            default=None,
            help="Process only this table name (requires --database for clarity).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=TIMEOUT,
            help=f"Per-request timeout in seconds (default: {TIMEOUT}).",
        )
        parser.add_argument(
            "--retries",
            type=int,
            default=RETRIES,
            help=f"Retry count per URL (default: {RETRIES}).",
        )
        parser.add_argument(
            "--log-file",
            type=str,
            default=None,
            help="Append failed URL log here (default: media/download_media_missing_links.txt).",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        only_alias: Optional[str] = options["database"]
        only_table: Optional[str] = options["table"]
        timeout: int = options["timeout"]
        retries: int = options["retries"]

        media_root = Path(getattr(settings, "MEDIA_ROOT", ""))
        if not media_root or not str(media_root):
            self.stderr.write(self.style.ERROR("MEDIA_ROOT is not set."))
            return

        media_root = media_root.resolve()
        log_default = media_root / "download_media_missing_links.txt"
        log_path = Path(options["log_file"] or log_default)

        aliases = [only_alias] if only_alias else list(connections)
        if only_table and not only_alias:
            self.stderr.write(self.style.ERROR("--table requires --database ALIAS"))
            return

        stats = {
            "urls_ok": 0,
            "urls_fail": 0,
            "rows_updated": 0,
            "cells_skipped_existing_file": 0,
        }
        failures: List[str] = []

        for alias in aliases:
            if alias not in connections:
                self.stdout.write(self.style.WARNING(f'Skip unknown database alias "{alias}"'))
                continue
            conn = connections[alias]
            db_name = conn.settings_dict.get("NAME", "") or alias
            safe_db = _safe_fs_segment(str(db_name))
            db_media = media_root / safe_db
            self.stdout.write(f"Database [{alias}] -> {db_name!r} -> {db_media}")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT TABLE_NAME FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                    """,
                    [db_name],
                )
                tables = [r[0] for r in cur.fetchall()]

            for table_name in tables:
                if only_table and table_name != only_table:
                    continue
                self._process_table(
                    alias,
                    db_name,
                    table_name,
                    media_root,
                    dry_run,
                    timeout,
                    retries,
                    stats,
                    failures,
                )

        # Write failure log
        ts = datetime.now().isoformat(timespec="seconds")
        header = f"\n--- run {ts} dry_run={dry_run} ---\n"
        log_lines = [header] + failures
        if not dry_run and failures:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.writelines(log_lines)
            self.stdout.write(self.style.WARNING(f"Logged {len(failures)} failure line(s) to {log_path}"))
        elif dry_run and failures:
            self.stdout.write(self.style.WARNING("(dry-run) would log failures:"))
            for line in failures[:50]:
                self.stdout.write(line.rstrip("\n"))
            if len(failures) > 50:
                self.stdout.write(f"... and {len(failures) - 50} more")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. downloads_ok={stats['urls_ok']} downloads_fail={stats['urls_fail']} "
                f"rows_updated={stats['rows_updated']} skipped_existing_file={stats['cells_skipped_existing_file']}"
            )
        )

    def _process_table(
        self,
        alias: str,
        db_name: str,
        table_name: str,
        media_root: Path,
        dry_run: bool,
        timeout: int,
        retries: int,
        stats: Dict[str, int],
        failures: List[str],
    ) -> None:
        conn = connections[alias]
        safe_db = _safe_fs_segment(str(db_name))
        safe_tbl = _safe_fs_segment(table_name)
        table_dir = media_root / safe_db / safe_tbl

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                """,
                [db_name, table_name],
            )
            col_info = {r[0]: (r[1] or "").lower() for r in cur.fetchall()}

        if "qid" not in col_info:
            return

        text_cols = [
            c
            for c, dt in col_info.items()
            if c != "qid" and dt in TEXT_TYPES
        ]
        if not text_cols:
            return

        cols_sql = ", ".join(f"`{c.replace('`', '``')}`" for c in ["qid"] + text_cols)
        safe_tn = table_name.replace("`", "``")

        with conn.cursor() as cur:
            cur.execute(f"SELECT {cols_sql} FROM `{safe_tn}`")
            rows = cur.fetchall()

        for row in rows:
            qid = row[0]
            if qid is None:
                continue
            qid_str = str(qid).strip()
            safe_qid = _safe_fs_segment(qid_str)
            if not safe_qid:
                continue

            col_values = list(row[1:])
            updates: Dict[str, str] = {}
            url_counter = 0
            row_url_map: Dict[str, str] = {}

            for col_name, val in zip(text_cols, col_values):
                if val is None or not isinstance(val, str) or "http" not in val.lower():
                    continue
                urls = _find_urls(val)
                if not urls:
                    continue
                new_text = val
                changed = False
                for url in urls:
                    if url in row_url_map:
                        rel_url = row_url_map[url]
                        if url in new_text:
                            new_text = new_text.replace(url, rel_url)
                            changed = True
                        continue

                    dest_base = table_dir / f"{safe_qid}_{url_counter}"
                    existing: Optional[Path] = None
                    if table_dir.is_dir():
                        matches = list(table_dir.glob(f"{safe_qid}_{url_counter}.*"))
                        if matches:
                            existing = matches[0]
                    if existing and existing.is_file():
                        rel_url = _relative_media_url(existing, media_root)
                        row_url_map[url] = rel_url
                        if url in new_text:
                            new_text = new_text.replace(url, rel_url)
                            changed = True
                        stats["cells_skipped_existing_file"] += 1
                        url_counter += 1
                        continue

                    if dry_run:
                        self.stdout.write(
                            f"[dry-run] {table_name} qid={qid_str[:60]}... col={col_name} -> {url[:80]}..."
                        )
                        url_counter += 1
                        continue

                    ok, info = download_with_retries(
                        url, dest_base, timeout=timeout, retries=retries
                    )
                    if ok:
                        dest_path = Path(info)
                        rel_url = _relative_media_url(dest_path, media_root)
                        row_url_map[url] = rel_url
                        if url in new_text:
                            new_text = new_text.replace(url, rel_url)
                            changed = True
                        stats["urls_ok"] += 1
                        url_counter += 1
                    else:
                        stats["urls_fail"] += 1
                        failures.append(
                            f"db={db_name} table={table_name} qid={qid_str} col={col_name} "
                            f"url={url}\n  error={info}\n"
                        )
                        url_counter += 1

                if changed and new_text != val:
                    updates[col_name] = new_text

            if not updates or dry_run:
                continue

            set_parts = []
            params: List[Any] = []
            for c, v in updates.items():
                set_parts.append(f"`{c.replace('`', '``')}` = %s")
                params.append(v)
            params.append(qid_str)
            sql = f"UPDATE `{safe_tn}` SET {', '.join(set_parts)} WHERE `qid` = %s"
            with conn.cursor() as cur:
                cur.execute(sql, params)
            stats["rows_updated"] += 1

        if rows:
            self.stdout.write(f"  table {table_name}: scanned {len(rows)} row(s)")
