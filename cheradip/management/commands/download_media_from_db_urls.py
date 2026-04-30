"""
Download http(s) assets referenced in string columns into MEDIA_ROOT/<db>/<table>/,
rename by qid, UPDATE rows on success; log failures with qid.

URLs are normalized to a strict ASCII + percent-encoding form: prose (e.g. Bengali) glued
immediately after a Firebase ``token=...`` value without a space is not part of the URL;
only the real https prefix is downloaded and replaced in the cell (following text is kept).

Skips downloading when the target ``<qid>_<n>.*`` file or per-URL cache ``u_<hash>.*`` already
exists under ``MEDIA_ROOT/<db>/<table>/`` (folder is created with ``exist_ok``).

Usage:
  python manage.py download_media_from_db_urls
  python manage.py download_media_from_db_urls --dry-run
  python manage.py download_media_from_db_urls --database hsc
  python manage.py download_media_from_db_urls --table cheradip_alim_11_12_al_fiqh_1st_paper

Resume / connectivity:
  Progress is saved under MEDIA_ROOT (see --state-file). After each row (ORDER BY qid), resume
  advances even when some URLs on that row fail, so an interrupted run can continue. Dead-link
  failures are appended to ``download_media_missing_links.txt`` (or ``--log-file``) as they occur.
  On connection timeouts and similar errors, the command waits 30 seconds and retries indefinitely.

  python manage.py download_media_from_db_urls --reset-state
  python manage.py download_media_from_db_urls --verbose   # extra progress (Django already uses -v for --verbosity)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections


@contextmanager
def _quiet_download_loggers() -> Iterator[None]:
    """Raise DB and HTTP client loggers to WARNING so SQL/urllib3 DEBUG does not hit cp1252 consoles."""
    names = (
        "django.db.backends",
        "django.db.backends.base",
        "django.db.backends.mysql",
        "django.db.backends.schema",
        "urllib3",
        "urllib3.connectionpool",
        "urllib3.util.retry",
    )
    prev: Dict[str, int] = {}
    for name in names:
        log = logging.getLogger(name)
        prev[name] = log.level
        log.setLevel(logging.WARNING)
    try:
        yield
    finally:
        for name, level in prev.items():
            logging.getLogger(name).setLevel(level)


# Broad scan for http(s); may include text accidentally glued after the URL (see _strict_http_url).
URL_RE = re.compile(r"https?://[^\s<\"\'\)\]\}]+", re.IGNORECASE)

# After a broad match, keep only RFC-style URL: ASCII + percent-encoding (drops e.g. Bengali glued to token=…).
_STRICT_URL_PREFIX = re.compile(
    r"^https?://"
    r"(?:[A-Za-z0-9\-._~:/?#\[\]@!$&\'()*+,;=]|%[0-9A-Fa-f]{2})+",
    re.IGNORECASE,
)

TEXT_TYPES = frozenset(
    {"varchar", "char", "text", "tinytext", "mediumtext", "longtext"}
)

RETRIES = 3
TIMEOUT = 120
NETWORK_WAIT_SECONDS = 30
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


def _strict_http_url(raw: str) -> str:
    """
    Cut at the end of a real URL when prose (e.g. Bengali) is glued without a space after
    e.g. ...token=uuidHere বর্তমানে — downloads must use the full valid https URL only.
    """
    m = _STRICT_URL_PREFIX.match(raw)
    if m:
        return m.group(0)
    return raw


def _find_urls(text: str) -> List[str]:
    if not text or "http" not in text.lower():
        return []
    seen: Set[str] = set()
    out: List[str] = []
    for m in URL_RE.finditer(text):
        u = _strict_http_url(m.group(0))
        u = _trim_url(u)
        if u.startswith("http://") or u.startswith("https://"):
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def _safe_fs_segment(name: str) -> str:
    bad = '<>:"/\\|?*'
    s = "".join(c if c not in bad else "_" for c in (name or ""))
    return s.strip() or "unnamed"


def _url_fingerprint(url: str) -> str:
    """Stable short id for `u_<fp>.*` cache files (same URL → skip re-download)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _find_cached_url_file(table_dir: Path, url: str) -> Optional[Path]:
    """Return existing `u_<fingerprint>.*` if present (from a prior run or earlier row)."""
    if not table_dir.is_dir():
        return None
    fp = _url_fingerprint(url)
    matches = list(table_dir.glob(f"u_{fp}.*"))
    if not matches:
        return None
    p = matches[0]
    return p if p.is_file() else None


def _existing_dest_file_for_slot(dest_base: Path) -> Optional[Path]:
    """First existing ``<dest_base.name>.*`` file in the same folder (saved as ``qid_n.ext``)."""
    parent = dest_base.parent
    if not parent.is_dir():
        return None
    for p in sorted(parent.glob(f"{dest_base.name}.*")):
        if p.is_file():
            return p
    return None


def _resolve_existing_saved_media(table_dir: Path, dest_base: Path, url: str) -> Optional[Path]:
    """URL cache ``u_<hash>.*`` or on-disk slot ``qid_n.*`` — skip re-download if either exists."""
    hit = _find_cached_url_file(table_dir, url)
    if hit is not None:
        return hit
    hit = _existing_dest_file_for_slot(dest_base)
    if hit is not None:
        return hit
    return None


def _store_url_cache_copy(table_dir: Path, url: str, saved_file: Path) -> None:
    """After a successful download to qid_n.ext, mirror to u_<hash>.<ext> for dedupe skips."""
    try:
        suffix = saved_file.suffix or ".bin"
        cache_path = table_dir / f"u_{_url_fingerprint(url)}{suffix}"
        if cache_path.resolve() == saved_file.resolve():
            return
        if cache_path.is_file():
            return
        try:
            os.link(saved_file, cache_path)
        except OSError:
            shutil.copy2(saved_file, cache_path)
    except OSError:
        pass


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
    # Avoid HTTP if ``<dest_without_ext.name>.*`` already exists (same naming as this command).
    for p in sorted(dest_without_ext.parent.glob(f"{dest_without_ext.name}.*")):
        if p.is_file():
            return True, str(p)
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


def _looks_like_network_error(message: str) -> bool:
    """Heuristic: treat as retry-after-wait when TCP/DNS/timeout style failures are reported."""
    if not message:
        return False
    m = message.lower()
    needles = (
        "connection aborted",
        "connection refused",
        "connection reset",
        "failed to establish a new connection",
        "max retries exceeded",
        "name or service not known",
        "network is unreachable",
        "no route to host",
        "temporary failure in name resolution",
        "timed out",
        "timeout",
        "unreachable",
        "errno 110",
        "errno 111",
        "errno 113",
        "errno 101",
        "errno -2",
        "sslerror",
        "certificate verify failed",
        "newconnectionerror",
        "gaierror",
    )
    return any(n in m for n in needles)


def _table_state_key(alias: str, db_name: str, table_name: str) -> str:
    return f"{alias}|{db_name}|{table_name}"


def _load_json_state(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """
    Write JSON state atomically where the OS allows it.

    On Windows, ``os.replace(tmp, path)`` often raises *PermissionError* if ``path`` already exists
    (file lock / indexer). We retry with short delays, try removing the target first, then fall
    back to ``shutil.copy2`` (non-atomic but reliable).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            try:
                f.flush()
                os.fsync(f.fileno())
            except OSError:
                pass

        last_err: Optional[BaseException] = None
        for attempt in range(12):
            try:
                if path.is_file():
                    try:
                        path.unlink()
                    except PermissionError as e:
                        last_err = e
                        time.sleep(0.05 * (attempt + 1))
                        continue
                os.replace(tmp, path)
                return
            except PermissionError as e:
                last_err = e
                time.sleep(0.05 * (attempt + 1))
            except OSError as e:
                last_err = e
                time.sleep(0.05 * (attempt + 1))

        try:
            shutil.copy2(tmp, path)
        except OSError as e:
            if last_err is not None:
                raise last_err from e
            raise
    finally:
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass


class DownloadResumeState:
    """Persist which (db, table, qid) finished so reruns skip completed rows (ORDER BY qid)."""

    STATE_VERSION = 1

    def __init__(
        self,
        path: Path,
        only_alias: Optional[str],
        only_table: Optional[str],
        dry_run: bool,
        reset: bool,
        stdout,
        style,
    ):
        self.path = path
        self.only_alias = only_alias
        self.only_table = only_table
        self.dry_run = dry_run
        self.stdout = stdout
        self.style = style
        if reset:
            self.data: Dict[str, Any] = self._fresh()
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        else:
            loaded = _load_json_state(path)
            if loaded and self._cli_matches_state(loaded):
                self.data = loaded
            else:
                if loaded:
                    stdout.write(
                        style.WARNING(
                            "Ignoring saved state (different --database / --table or unreadable); "
                            "starting from the beginning."
                        )
                    )
                self.data = self._fresh()

    def _fresh(self) -> Dict[str, Any]:
        return {
            "version": self.STATE_VERSION,
            "only_alias": self.only_alias,
            "only_table": self.only_table,
            "skip_tables": [],
            "resume": {},
        }

    def _cli_matches_state(self, data: Dict[str, Any]) -> bool:
        return (
            data.get("only_alias") == self.only_alias
            and data.get("only_table") == self.only_table
            and int(data.get("version", 0)) == self.STATE_VERSION
        )

    def should_skip_table(self, alias: str, db_name: str, table_name: str) -> bool:
        return _table_state_key(alias, db_name, table_name) in set(self.data.get("skip_tables") or [])

    def resume_after_qid(self, alias: str, db_name: str, table_name: str) -> Any:
        r = self.data.get("resume") or {}
        if (
            r.get("alias") == alias
            and r.get("db_name") == db_name
            and r.get("table") == table_name
        ):
            v = r.get("last_qid_processed")
            if v is None or v == "":
                return None
            return v
        return None

    def save_after_row(self, alias: str, db_name: str, table_name: str, qid_value: Any) -> None:
        if self.dry_run:
            return
        self.data["only_alias"] = self.only_alias
        self.data["only_table"] = self.only_table
        self.data["resume"] = {
            "alias": alias,
            "db_name": db_name,
            "table": table_name,
            "last_qid_processed": qid_value,
        }
        _atomic_write_json(self.path, self.data)

    def mark_table_complete(self, alias: str, db_name: str, table_name: str) -> None:
        if self.dry_run:
            return
        key = _table_state_key(alias, db_name, table_name)
        st = self.data.setdefault("skip_tables", [])
        if key not in st:
            st.append(key)
        self.data["resume"] = {}
        self.data["only_alias"] = self.only_alias
        self.data["only_table"] = self.only_table
        _atomic_write_json(self.path, self.data)

    def clear_on_full_success(self) -> None:
        if self.dry_run:
            return
        if self.path.is_file():
            try:
                self.path.unlink()
            except OSError:
                pass


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
        "download to media/<db>/<table>/; UPDATE cells on success; append failures to the log file "
        "and continue through all rows in each table."
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
            help="Append each failed URL here as it occurs (default: MEDIA_ROOT/download_media_missing_links.txt).",
        )
        parser.add_argument(
            "--state-file",
            type=str,
            default=None,
            help="JSON resume cursor (default: MEDIA_ROOT/download_media_from_db_urls_state.json).",
        )
        parser.add_argument(
            "--reset-state",
            action="store_true",
            help="Delete resume state and start from the first row again.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-table progress, dry-run lines, resume notices, and each network wait.",
        )

    def handle(self, *args, **options):
        with _quiet_download_loggers():
            self._handle_download_media(options)

    def _handle_download_media(self, options: Dict[str, Any]) -> None:
        dry_run: bool = options["dry_run"]
        self._download_verbose = bool(options["verbose"])
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
        state_path = Path(options["state_file"] or (media_root / "download_media_from_db_urls_state.json"))
        state_path = state_path.resolve()
        verbose: bool = self._download_verbose

        state = DownloadResumeState(
            state_path,
            only_alias,
            only_table,
            dry_run,
            bool(options["reset_state"]),
            self.stdout,
            self.style,
        )
        if verbose and not dry_run and state_path.is_file() and not options["reset_state"]:
            self.stdout.write(self.style.NOTICE(f"Resume state: {state_path}"))

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
        self._failure_log_run_ts = datetime.now().isoformat(timespec="seconds")
        self._failure_log_header_written = False

        for alias in aliases:
            if alias not in connections:
                # self.stdout.write(self.style.WARNING(f'Skip unknown database alias "{alias}"'))
                continue
            conn = connections[alias]
            db_name = conn.settings_dict.get("NAME", "") or alias
            safe_db = _safe_fs_segment(str(db_name))
            db_media = media_root / safe_db
            # self.stdout.write(f"Database [{alias}] -> {db_name!r} -> {db_media}")

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
                if state.should_skip_table(alias, db_name, table_name):
                    if verbose:
                        self.stdout.write(
                            self.style.NOTICE(f"  [{alias}] skip completed table `{table_name}` (resume)")
                        )
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
                    state,
                    verbose,
                    log_path,
                )

        # Failure log: each URL failure is appended during the run (see _append_failure_log_line).
        # Batch-write here only if nothing was flushed (e.g. dry-run keeps failures in memory only).
        if not dry_run and failures and not self._failure_log_header_written:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            header = f"\n--- run {self._failure_log_run_ts} dry_run={dry_run} ---\n"
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(header)
                lf.writelines(failures)
        elif dry_run and failures:
            if verbose:
                self.stdout.write(self.style.WARNING("(dry-run) would log failures:"))
                for line in failures[:50]:
                    self.stdout.write(line.rstrip("\n"))
                if len(failures) > 50:
                    self.stdout.write(f"... and {len(failures) - 50} more")
            else:
                self.stdout.write(
                    self.style.WARNING(f"(dry-run) {len(failures)} failure line(s); use --verbose to print.")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. downloads_ok={stats['urls_ok']} downloads_fail={stats['urls_fail']} "
                f"rows_updated={stats['rows_updated']} skipped_existing_file={stats['cells_skipped_existing_file']}"
            )
        )
        if not dry_run and failures:
            self.stdout.write(
                self.style.WARNING(f"{len(failures)} URL failure(s) logged to {log_path}")
            )
        if not dry_run and not failures:
            state.clear_on_full_success()
            if verbose:
                self.stdout.write(
                    self.style.NOTICE("Cleared resume state (completed with no download failures).")
                )

    def _append_failure_log_line(self, log_path: Path, line: str, dry_run: bool) -> None:
        """Append one failure record to the log file as soon as it occurs (not dry-run only)."""
        if dry_run:
            return
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            if not self._failure_log_header_written:
                lf.write(f"\n--- run {self._failure_log_run_ts} dry_run=False ---\n")
                self._failure_log_header_written = True
            lf.write(line)
            lf.flush()

    def _download_with_network_wait(
        self, url: str, dest: Path, timeout: int, retries: int
    ) -> Tuple[bool, str]:
        """Retry on transient per-URL failures; on network-style errors wait and retry indefinitely."""
        while True:
            ok, msg = download_with_retries(url, dest, timeout=timeout, retries=retries)
            if ok:
                return True, msg
            if _looks_like_network_error(msg):
                if self._download_verbose:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Network/connectivity issue — retrying in {NETWORK_WAIT_SECONDS}s: {msg[:280]}"
                        )
                    )
                time.sleep(NETWORK_WAIT_SECONDS)
                continue
            return False, msg

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
        state: DownloadResumeState,
        verbose: bool,
        log_path: Path,
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

        resume_qid = state.resume_after_qid(alias, db_name, table_name)
        select_params: List[Any] = []
        if resume_qid is not None:
            where_sql = " WHERE `qid` > %s"
            select_params.append(resume_qid)
        else:
            where_sql = ""
        select_sql = f"SELECT {cols_sql} FROM `{safe_tn}`{where_sql} ORDER BY `qid` ASC"

        with conn.cursor() as cur:
            cur.execute(select_sql, select_params)
            rows = cur.fetchall()

        table_dir.mkdir(parents=True, exist_ok=True)

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
            row_download_fail = False

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
                    existing_media = _resolve_existing_saved_media(table_dir, dest_base, url)
                    if existing_media is not None:
                        rel_url = _relative_media_url(existing_media, media_root)
                        row_url_map[url] = rel_url
                        if url in new_text:
                            new_text = new_text.replace(url, rel_url)
                            changed = True
                        stats["cells_skipped_existing_file"] += 1
                        url_counter += 1
                        continue

                    if dry_run:
                        if verbose:
                            self.stdout.write(
                                f"[dry-run] {table_name} qid={qid_str[:60]}... col={col_name} -> {url[:80]}..."
                            )
                        url_counter += 1
                        continue

                    ok, info = self._download_with_network_wait(
                        url, dest_base, timeout=timeout, retries=retries
                    )
                    if ok:
                        dest_path = Path(info)
                        _store_url_cache_copy(table_dir, url, dest_path)
                        rel_url = _relative_media_url(dest_path, media_root)
                        row_url_map[url] = rel_url
                        if url in new_text:
                            new_text = new_text.replace(url, rel_url)
                            changed = True
                        stats["urls_ok"] += 1
                        url_counter += 1
                    else:
                        stats["urls_fail"] += 1
                        row_download_fail = True
                        fail_line = (
                            f"db={db_name} table={table_name} qid={qid_str} col={col_name} "
                            f"url={url}\n  error={info}\n"
                        )
                        failures.append(fail_line)
                        self._append_failure_log_line(log_path, fail_line, dry_run)
                        url_counter += 1

                if changed and new_text != val:
                    updates[col_name] = new_text

            if updates and not dry_run:
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

            if row_download_fail and verbose:
                self.stdout.write(
                    self.style.NOTICE(
                        f"`{table_name}` qid={qid_str}: URL failure(s) logged; continuing table."
                    )
                )

            if not dry_run:
                state.save_after_row(alias, db_name, table_name, qid)

        if rows and verbose:
            self.stdout.write(f"  table {table_name}: scanned {len(rows)} row(s)")
        if not dry_run:
            state.mark_table_complete(alias, db_name, table_name)
