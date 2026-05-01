"""
MySQL/MariaDB sync between local and remote (``mysqldump`` | ``mysql``).

**What ``--l2r`` / ``--r2l`` do**

- **``--l2r`` (local → remote):** Discovers databases on **local** (respecting
  ``SYNC_DATABASES`` / ``EXCLUDE_DATABASES``), then for each database runs
  ``mysqldump`` on local and streams the result into ``mysql`` on **remote**.
  That dump includes **all tables**, views (if any), **all row data**, plus
  routines, triggers, and events (see dump flags below).

- **``--r2l`` (remote → local):** Same flow with **remote** as the source and
  **local** as the destination.

**Databases on the destination**

Before each restore, the command runs
``CREATE DATABASE IF NOT EXISTS`` on the destination so a missing database
is created. The dump uses ``--no-create-db`` so the pipe does not rely on a
bare ``CREATE DATABASE`` statement from ``mysqldump``.

**Tables and data**

``mysqldump`` defaults (via ``--opt``) include **``DROP TABLE IF EXISTS``** before
each ``CREATE TABLE`` and then the inserts. So:

- On an **empty** destination, tables and data are **created** from the source.
- If a table **already exists**, it is **dropped and recreated**, then filled
  from the source — the destination table becomes a **full copy** of the source,
  not a row-by-row “only if missing” merge.

If you need merge / incremental behaviour, use replication, ``pt-table-sync``,
or application-level tools; this command is a **full snapshot** per database.

**Django**

::

    python manage.py mysql_db_sync --l2r
    python manage.py mysql_db_sync --r2l
    python manage.py mysql_db_sync --l2r --watch --interval 600

**Module CLI** (from project root, ``PYTHONPATH`` must include the project)::

    python -m cheradip.management.commands.mysql_db_sync --direction local-to-remote

**Configuration** — defaults are defined in this file (``DEFAULT_SYNC_*``); override
with environment variables or ``scripts/.env.db-sync`` / ``.env.db-sync`` at the project
root (optional: ``pip install python-dotenv``).

- ``REMOTE_HOST``, ``REMOTE_PORT``, ``REMOTE_USER``, ``REMOTE_PASSWORD`` — fall back to in-file defaults
- ``LOCAL_HOST`` (default ``127.0.0.1``), ``LOCAL_PORT``, ``LOCAL_USER``, ``LOCAL_PASSWORD``
- ``SYNC_DIRECTION``: ``local-to-remote`` or ``remote-to-local`` (module CLI only; manage uses ``--l2r`` / ``--r2l``)
- ``WATCH``, ``WATCH_INTERVAL_SECONDS`` — periodic full re-sync (snapshot, not replication)
- ``MYSQLDUMP_PATH``, ``MYSQL_PATH`` — overrides if clients not on ``PATH``
- ``MYSQL_SYNC_USE_TEMPFILE`` — ``1``/``true`` = dump to a temp file then import (default **on** on
  Windows; avoids broken-pipe ``errno 22``/``32`` when the remote server stops reading). ``0`` = pipe mode.
- ``MYSQL_SYNC_SKIP_REMOTE_ACCESS_CHECK`` — ``1`` = do not pre-check remote ``USE`` for ``--l2r`` (default off).
- ``SYNC_DATABASES`` — comma-separated allow list. Leave unset / empty / ``*`` in code (``DEFAULT_SYNC_DATABASES``)
  to sync **every** non-excluded database found on the source. Set to e.g. ``cheradip_cheradip`` when the remote
  user may only access one database (avoids 1044 errors on ``CREATE DATABASE`` for other names).
- ``EXCLUDE_DATABASES`` — extra names to skip
- ``DRY_RUN`` — print only, no copy

**Invalid names (skipped automatically)**

Names that look like legacy data-directory junk (e.g. ``#mysql50#...`` or containing ``.corrupt``)
cannot be created on a normal server with ``CREATE DATABASE`` — they are omitted from the sync list.
"""

from __future__ import annotations

import argparse
import os
import socket
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# ---------------------------------------------------------------------------
# mysql_db_sync defaults — edit here for quick sync without .env
# Environment variables (or dotenv) still override these when set.
# ---------------------------------------------------------------------------
DEFAULT_SYNC_REMOTE_HOST = "cheradip.com"
DEFAULT_SYNC_REMOTE_PORT = "3306"
DEFAULT_SYNC_REMOTE_USER = "cheradip_cheradip"
DEFAULT_SYNC_REMOTE_PASSWORD = "Sa@2271029867"

DEFAULT_SYNC_LOCAL_HOST = "127.0.0.1"
DEFAULT_SYNC_LOCAL_PORT = "3306"
DEFAULT_SYNC_LOCAL_USER = "root"
DEFAULT_SYNC_LOCAL_PASSWORD = ""  # empty = no password (typical XAMPP root)
# Comma-separated database names to sync, or "" / "*" = sync all non-excluded DBs on the source (default).
# Set to e.g. "cheradip_cheradip" if your remote MySQL user may only touch one database.
DEFAULT_SYNC_DATABASES = ""
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDE = frozenset(
    {
        "information_schema",
        "mysql",
        "performance_schema",
        "sys",
        "phpmyadmin",
        "test",  # common local scratch DB; remove via SYNC_DATABASES if you must sync it
    }
)


def _is_syncable_database_name(name: str) -> bool:
    """
    False for legacy / corrupt folder names that SHOW DATABASES may still list (e.g. XAMPP)
    but ``CREATE DATABASE`` rejects (ERROR 1102 Incorrect database name).
    """
    if not name or not name.strip():
        return False
    # MySQL 5.0 directory-prefix leftovers; '#' is not usable as a normal schema name on many hosts.
    if name.startswith("#mysql50#"):
        return False
    if ".corrupt" in name.lower():
        return False
    return True


class MySQLSyncError(Exception):
    """User-facing sync failure (config, mysqldump, or mysql restore)."""


def load_dotenv(search_dirs: list[Path]) -> None:
    for base in search_dirs:
        for name in (".env.db-sync", "env.db-sync"):
            p = base / name
            if not p.is_file():
                continue
            try:
                from dotenv import load_dotenv  # type: ignore

                load_dotenv(p)
                print(f"Loaded: {p}")
                return
            except ImportError:
                print("Optional: pip install python-dotenv to load .env.db-sync automatically.")
                return


def env(key: str, default: str | None = None) -> str | None:
    v = os.environ.get(key)
    if v is not None and str(v).strip() != "":
        return str(v).strip()
    return default


def env_bool(key: str, default: bool = False) -> bool:
    v = env(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "y", "on")


def env_int(key: str, default: int) -> int:
    v = env(key)
    if v is None:
        return default
    try:
        return max(1, int(v.strip()))
    except ValueError:
        return default


def find_client(name: str, override: str | None) -> str | None:
    if override:
        p = Path(override)
        if p.is_file():
            return str(p)
        print(f"WARN: {name} override not found: {override}")
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "win32":
        xampp = Path(r"C:\xampp\mysql\bin") / f"{name}.exe"
        if xampp.is_file():
            return str(xampp)
    return None


def mysql_base_args(host: str, port: str, user: str, password: str | None) -> list[str]:
    # Force UTF-8 session charset to avoid mojibake during dump/import on Windows clients.
    args = [
        "--protocol=TCP",
        "--default-character-set=utf8mb4",
        f"-h{host}",
        f"-P{port}",
        f"-u{user}",
    ]
    if password:
        args.append(f"-p{password}")
    else:
        args.append("--password=")
    return args


def list_databases(mysql: str, host: str, port: str, user: str, password: str | None) -> list[str]:
    cmd = [mysql, *mysql_base_args(host, port, user, password), "-N", "-e", "SHOW DATABASES;"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise MySQLSyncError(
            f"Listing databases on {host}:{port} failed:\n{r.stderr or r.stdout}"
        )
    out = []
    for line in (r.stdout or "").splitlines():
        name = line.strip()
        if name:
            out.append(name)
    return sorted(out)


def parse_csv(s: str | None) -> set[str]:
    if not s:
        return set()
    return {x.strip() for x in s.split(",") if x.strip()}


_mysqldump_help_text_cache: dict[str, str] = {}


def _mysqldump_help_text(mysqldump: str) -> str:
    """Cached ``mysqldump --help`` text (older XAMPP clients omit some flags)."""
    if mysqldump not in _mysqldump_help_text_cache:
        r = subprocess.run([mysqldump, "--help"], capture_output=True, text=True, timeout=15)
        _mysqldump_help_text_cache[mysqldump] = (r.stdout or "") + (r.stderr or "")
    return _mysqldump_help_text_cache[mysqldump]


def mysqldump_supports_column_statistics(mysqldump: str) -> bool:
    return "column-statistics" in _mysqldump_help_text(mysqldump).lower()


def mysqldump_supports_set_gtid_purged(mysqldump: str) -> bool:
    h = _mysqldump_help_text(mysqldump).lower()
    return "set-gtid-purged" in h


def build_dump_prefix(
    mysqldump: str,
    source_host: str,
    source_port: str,
    source_user: str,
    source_password: str | None,
) -> list[str]:
    dump_common = [
        mysqldump,
        *mysql_base_args(source_host, source_port, source_user, source_password),
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--default-character-set=utf8mb4",
    ]
    if mysqldump_supports_set_gtid_purged(mysqldump):
        dump_common.insert(-1, "--set-gtid-purged=OFF")
    if mysqldump_supports_column_statistics(mysqldump):
        dump_common.append("--column-statistics=0")
    return dump_common


def _redact(cmd: list[str]) -> list[str]:
    out = []
    for a in cmd:
        if a.startswith("-p") and len(a) > 2:
            out.append("-p***")
        else:
            out.append(a)
    return out


def _quote_db_ident(db: str) -> str:
    """Backtick-quote a database name (escape embedded backticks)."""
    if not db.strip():
        raise MySQLSyncError("Empty database name.")
    return "`" + db.replace("`", "``") + "`"


def remote_mysql_can_use_database(
    mysql: str,
    host: str,
    port: str,
    user: str,
    password: str | None,
    db: str,
) -> bool:
    """
    Return False only when the server clearly denies this user that database (1044 / access denied).

    Returns True on success or on errors like “unknown database” so ``--l2r`` can still try
    ``CREATE DATABASE`` + import when the schema does not exist yet.
    """
    cmd = [
        mysql,
        *mysql_base_args(host, port, user, password),
        db,
        "-e",
        "SELECT 1;",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        return True
    err = ((r.stderr or "") + (r.stdout or "")).lower()
    if "1044" in err or ("access denied" in err and "database" in err):
        return False
    return True


def ensure_destination_database(
    mysql: str,
    dest_host: str,
    dest_port: str,
    dest_user: str,
    dest_password: str | None,
    db: str,
    dry: bool,
) -> bool:
    """
    Create destination database if missing.

    Returns True if created, already existed, or dry-run.
    Returns False if skipped (e.g. ER_DBACCESS_DENIED_ERROR 1044 — user cannot CREATE that
    database on shared hosting); import may still succeed if the DB already exists.
    """
    if dry:
        return True
    ident = _quote_db_ident(db)
    sql = f"CREATE DATABASE IF NOT EXISTS {ident} /*!40100 DEFAULT CHARACTER SET utf8mb4 */;"
    cmd = [
        mysql,
        *mysql_base_args(dest_host, dest_port, dest_user, dest_password),
        "-e",
        sql,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode == 0:
        return True
    err = (r.stderr or r.stdout or "").strip()
    # Shared hosting: app user may only use one pre-created database
    if "1044" in err or ("Access denied" in err and "database" in err.lower()):
        print(
            f"    WARN: Skipping CREATE DATABASE for `{db}` (no privilege). "
            "If this database already exists on the destination, import continues."
        )
        return False
    raise MySQLSyncError(f"CREATE DATABASE IF NOT EXISTS failed for {db}:\n{err}")


def _use_tempfile_for_sync() -> bool:
    """Temp file avoids Windows pipe breaks when remote ``mysql`` exits early (e.g. 1044)."""
    return env_bool("MYSQL_SYNC_USE_TEMPFILE", sys.platform == "win32")


def _is_network_error_message(msg: str) -> bool:
    """
    Heuristic: detect transient connectivity/DNS/timeouts from mysql/mysqldump errors.
    """
    m = msg.lower()
    needles = (
        "can't connect",
        "cannot connect",
        "connection refused",
        "lost connection",
        "server has gone away",
        "timed out",
        "timeout",
        "network is unreachable",
        "no route to host",
        "temporary failure in name resolution",
        "getaddrinfo",
        "unknown mysql server host",
        "communications link failure",
        "connection reset",
        "ssl connection error",
    )
    return any(n in m for n in needles)


def _wait_for_connectivity(check_points: list[tuple[str, str]]) -> None:
    """
    Block until at least one DB endpoint is reachable again, checking every 30 seconds.
    """
    print("    [NET] Network issue detected. Waiting for connectivity (check every 30s)...")
    while True:
        for host, port in check_points:
            try:
                with socket.create_connection((host, int(port)), timeout=8):
                    print(f"    [NET] Connectivity restored via {host}:{port}. Resuming...")
                    return
            except OSError:
                continue
        print("    [NET] Still offline/unreachable. Retrying in 30 seconds...")
        time.sleep(30)


def sync_one_database(
    *,
    mysqldump: str,
    mysql: str,
    source_host: str,
    source_port: str,
    source_user: str,
    source_password: str | None,
    dest_host: str,
    dest_port: str,
    dest_user: str,
    dest_password: str | None,
    db: str,
    dry: bool,
) -> None:
    # Ensure destination schema exists; dump omits CREATE DATABASE (--no-create-db).
    ensure_destination_database(
        mysql, dest_host, dest_port, dest_user, dest_password, db, dry
    )
    dump_cmd = build_dump_prefix(mysqldump, source_host, source_port, source_user, source_password) + [
        "--databases",
        "--no-create-db",
        db,
    ]
    dest_mysql = [mysql, *mysql_base_args(dest_host, dest_port, dest_user, dest_password)]

    if dry:
        print("[DRY_RUN] Would run:", " ".join(_redact(dump_cmd)) + " | mysql ...")
        return

    if _use_tempfile_for_sync():
        _sync_one_database_via_tempfile(dump_cmd, dest_mysql, db)
        return

    print("    … mysqldump | mysql (pipe; set MYSQL_SYNC_USE_TEMPFILE=1 on Windows if this fails) …")
    dump_p = subprocess.Popen(
        dump_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    restore_p = subprocess.Popen(
        dest_mysql,
        stdin=dump_p.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert dump_p.stdout is not None
    dump_p.stdout.close()
    out_r, err_r = restore_p.communicate()
    err_d = b""
    if dump_p.stderr:
        err_d = dump_p.stderr.read()
    dump_p.wait()

    dstderr = err_d.decode("utf-8", errors="replace")
    rstderr = (err_r or b"").decode("utf-8", errors="replace")

    if restore_p.returncode != 0:
        msg = f"mysql (destination) failed:\n{rstderr[:6000]}"
        if dump_p.returncode != 0:
            msg += f"\n--- mysqldump exited {dump_p.returncode}:\n{dstderr[:4000]}"
        raise MySQLSyncError(msg)

    if dump_p.returncode != 0:
        hint = ""
        low = dstderr.lower()
        if "errno 22" in dstderr or "errno 32" in dstderr or "broken pipe" in low:
            hint = (
                "\n--- Hint: errno 22/32 / broken pipe usually means the destination closed the "
                "connection (often ERROR 1044: no privilege for that database). "
                "On Windows, set MYSQL_SYNC_USE_TEMPFILE=1 (default) to see the real mysql error. ---"
            )
        raise MySQLSyncError("mysqldump failed:\n" + dstderr[:4000] + hint)

    print("    OK:", (out_r or b"").decode("utf-8", errors="replace").strip()[:200])


def _sync_one_database_via_tempfile(dump_cmd: list[str], dest_mysql: list[str], db: str) -> None:
    fd, tmp_path = tempfile.mkstemp(prefix="mysql_db_sync_", suffix=f"_{db}.sql")
    os.close(fd)
    try:
        print("    … mysqldump to temp file (then import; clearer errors if remote rejects the DB) …")
        with open(tmp_path, "wb") as dump_out:
            r_dump = subprocess.run(
                dump_cmd,
                stdout=dump_out,
                stderr=subprocess.PIPE,
                timeout=None,
            )
        if r_dump.returncode != 0:
            err = (r_dump.stderr or b"").decode("utf-8", errors="replace")[:6000]
            raise MySQLSyncError(f"mysqldump failed:\n{err}")

        size = os.path.getsize(tmp_path)
        if size == 0:
            raise MySQLSyncError("mysqldump produced an empty file (nothing to import).")
        mib = size / (1024 * 1024)
        print(f"    … dump {mib:.2f} MiB, importing to destination …")

        with open(tmp_path, "rb") as dump_in:
            r_mysql = subprocess.run(
                dest_mysql,
                stdin=dump_in,
                capture_output=True,
                timeout=None,
            )
        if r_mysql.returncode != 0:
            err = (r_mysql.stderr or r_mysql.stdout or b"").decode("utf-8", errors="replace")[:8000]
            raise MySQLSyncError(
                "mysql (destination) failed:\n"
                + err
                + "\n--- If you see 1044, this MySQL user cannot write that database on the server "
                "(hosting often allows only one DB name). Use SYNC_DATABASES=cheradip_cheradip or "
                "ask the host to grant access to each schema. ---"
            )
        out = (r_mysql.stdout or b"").decode("utf-8", errors="replace").strip()[:200]
        print("    OK:", out)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def resolve_databases(
    mysql: str,
    list_host: str,
    list_port: str,
    list_user: str,
    list_password: str | None,
    only: set[str],
    extra_exclude: set[str],
) -> list[str]:
    all_names = list_databases(mysql, list_host, list_port, list_user, list_password)
    to_sync: list[str] = []
    skipped_invalid: list[str] = []
    for db in all_names:
        if not _is_syncable_database_name(db):
            skipped_invalid.append(db)
            continue
        if only and db not in only:
            continue
        if db in DEFAULT_EXCLUDE | extra_exclude and not (only and db in only):
            continue
        to_sync.append(db)
    if skipped_invalid:
        print(
            "Skipping invalid / non-createable database name(s) (legacy #mysql50#, .corrupt, etc.):\n  "
            + ", ".join(skipped_invalid)
        )
    return to_sync


def run_one_pass(
    *,
    direction: str,
    mysqldump: str,
    mysql: str,
    local_host: str,
    local_port: str,
    local_user: str,
    local_password: str | None,
    remote_host: str,
    remote_port: str,
    remote_user: str,
    remote_password: str | None,
    to_sync: list[str],
    dry: bool,
) -> tuple[int, int]:
    """
    Sync each database in ``to_sync``. Returns (success_count, failure_count).
    """
    if direction == "local-to-remote":
        src_h, src_p, src_u, src_pw = local_host, local_port, local_user, local_password
        dst_h, dst_p, dst_u, dst_pw = remote_host, remote_port, remote_user, remote_password
        label = "LOCAL → REMOTE"
    else:
        src_h, src_p, src_u, src_pw = remote_host, remote_port, remote_user, remote_password
        dst_h, dst_p, dst_u, dst_pw = local_host, local_port, local_user, local_password
        label = "REMOTE → LOCAL"

    n = len(to_sync)
    print(f"\n=== Pass: {label} @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"--- Databases in this pass: {n} (progress: current/total, remaining after this step) ---")

    ok = 0
    failed = 0
    network_checks = [(src_h, src_p), (dst_h, dst_p)]
    max_retries = 3
    for idx, db in enumerate(to_sync, start=1):
        remaining_after = n - idx
        print(f"\n>>> [{idx}/{n}] {db}  —  remaining after this: {remaining_after}")
        retry_count = 0
        while True:
            try:
                if retry_count > 0:
                    print(f"    [RETRY] Attempt {retry_count + 1}/{max_retries + 1} for {db}")
                sync_one_database(
                    mysqldump=mysqldump,
                    mysql=mysql,
                    source_host=src_h,
                    source_port=src_p,
                    source_user=src_u,
                    source_password=src_pw,
                    dest_host=dst_h,
                    dest_port=dst_p,
                    dest_user=dst_u,
                    dest_password=dst_pw,
                    db=db,
                    dry=dry,
                )
                ok += 1
                print(f"    [OK] Finished [{idx}/{n}] {db}")
                break
            except MySQLSyncError as e:
                err = str(e)
                if _is_network_error_message(err):
                    # Do not advance stage/index; wait and retry the same database.
                    _wait_for_connectivity(network_checks)
                    continue
                if retry_count < max_retries:
                    retry_count += 1
                    print(
                        f"    [WARN] Non-network error for {db}; retrying "
                        f"({retry_count}/{max_retries})..."
                    )
                    print(f"    [DETAIL] {err[:600]}")
                    time.sleep(2)
                    continue
                failed += 1
                print(f"    [FAIL] [{idx}/{n}] {db} after {max_retries} retries:\n{err}")
                break

    print(f"\n--- Pass summary: {ok} succeeded, {failed} failed (of {n}) ---")
    return ok, failed


def run_sync(
    *,
    direction: str,
    watch: bool,
    interval: int | None,
    dotenv_dirs: list[Path],
) -> int:
    """
    Run one or more sync passes. Returns 0 on success, 2 on misconfiguration, 1 on failure.
    Watch mode returns 0 on Ctrl+C.
    """
    load_dotenv(dotenv_dirs)
    if interval is None:
        interval = env_int("WATCH_INTERVAL_SECONDS", 300)

    remote_host = env("REMOTE_HOST", DEFAULT_SYNC_REMOTE_HOST)
    remote_user = env("REMOTE_USER", DEFAULT_SYNC_REMOTE_USER)
    remote_password = env("REMOTE_PASSWORD", DEFAULT_SYNC_REMOTE_PASSWORD)
    remote_port = env("REMOTE_PORT", DEFAULT_SYNC_REMOTE_PORT) or "3306"

    local_host = env("LOCAL_HOST", DEFAULT_SYNC_LOCAL_HOST) or DEFAULT_SYNC_LOCAL_HOST
    local_user = env("LOCAL_USER", DEFAULT_SYNC_LOCAL_USER) or DEFAULT_SYNC_LOCAL_USER
    local_password = env("LOCAL_PASSWORD", DEFAULT_SYNC_LOCAL_PASSWORD) or ""
    local_port = env("LOCAL_PORT", DEFAULT_SYNC_LOCAL_PORT) or "3306"

    if not remote_host or not remote_user or remote_password is None:
        print(
            "ERROR: Remote host, user, and password are missing. "
            "Set DEFAULT_SYNC_* in mysql_db_sync.py or REMOTE_* in the environment / .env.db-sync."
        )
        return 2

    mysqldump = find_client("mysqldump", env("MYSQLDUMP_PATH"))
    mysql = find_client("mysql", env("MYSQL_PATH"))
    if not mysqldump or not mysql:
        print(
            "ERROR: mysqldump and/or mysql not found. Set MYSQLDUMP_PATH / MYSQL_PATH\n"
            "  (e.g. C:\\xampp\\mysql\\bin\\mysqldump.exe)."
        )
        return 2

    dry = env_bool("DRY_RUN", False)
    sync_raw = (env("SYNC_DATABASES", DEFAULT_SYNC_DATABASES) or "").strip()
    if sync_raw in ("*", ""):
        only = set()
    else:
        only = parse_csv(sync_raw)
    extra_exclude = parse_csv(env("EXCLUDE_DATABASES"))

    direction = direction.strip().lower()
    if direction not in ("local-to-remote", "remote-to-local"):
        print("ERROR: direction must be local-to-remote or remote-to-local")
        return 2

    list_host = local_host if direction == "local-to-remote" else remote_host
    list_port = local_port if direction == "local-to-remote" else remote_port
    list_user = local_user if direction == "local-to-remote" else remote_user
    list_pw = (local_password or None) if direction == "local-to-remote" else remote_password

    print("Direction:", direction)
    if only:
        print("Database filter: SYNC_DATABASES / DEFAULT_SYNC_DATABASES =", ", ".join(sorted(only)))
    else:
        print("Database filter: all non-excluded databases on source")
    print(f"List DBs from: {list_user}@{list_host}:{list_port}")
    print(f"Local:  {local_user}@{local_host}:{local_port}")
    print(f"Remote: {remote_user}@{remote_host}:{remote_port}")
    print(f"Using:  mysqldump={mysqldump}\n        mysql={mysql}")
    if _use_tempfile_for_sync():
        print("Dump mode: temp file (default on Windows; MYSQL_SYNC_USE_TEMPFILE=0 for pipe)")
    else:
        print("Dump mode: pipe (mysqldump | mysql)")
    if dry:
        print("DRY_RUN=1 — no data will be copied.\n")
    if watch:
        print(f"Watch mode: interval={interval}s (Ctrl+C to stop)\n")

    try:
        to_sync = resolve_databases(mysql, list_host, list_port, list_user, list_pw, only, extra_exclude)
    except MySQLSyncError as e:
        print("ERROR:", e)
        return 1

    if not to_sync:
        print("No databases to sync (check SYNC_DATABASES / excludes).")
        return 0

    if (
        direction == "local-to-remote"
        and not dry
        and not env_bool("MYSQL_SYNC_SKIP_REMOTE_ACCESS_CHECK", False)
    ):
        kept: list[str] = []
        skipped_remote: list[str] = []
        for db in to_sync:
            if remote_mysql_can_use_database(
                mysql, remote_host, remote_port, remote_user, remote_password, db
            ):
                kept.append(db)
            else:
                skipped_remote.append(db)
        if skipped_remote:
            print(
                "\nPre-flight (remote): skipping databases this user cannot USE "
                "(would fail with ERROR 1044 after a large dump):\n  "
                + ", ".join(skipped_remote)
            )
            print(
                "  Ask the host to GRANT privileges on those schemas to "
                f"'{remote_user}', or list only allowed DBs in SYNC_DATABASES.\n"
            )
        to_sync = kept
        if not to_sync:
            print("Nothing to push: no local database names are writable on the remote for this user.")
            return 0

    print(f"Databases to sync ({len(to_sync)}):", ", ".join(to_sync))
    print("---")

    try:
        while True:
            ok, failed = run_one_pass(
                direction=direction,
                mysqldump=mysqldump,
                mysql=mysql,
                local_host=local_host,
                local_port=local_port,
                local_user=local_user,
                local_password=local_password or None,
                remote_host=remote_host,
                remote_port=remote_port,
                remote_user=remote_user,
                remote_password=remote_password,
                to_sync=to_sync,
                dry=dry,
            )
            print("\nPass finished.")
            if failed > 0 and ok == 0:
                print("ERROR: Every database in this pass failed.")
                return 1
            if failed > 0:
                print(
                    f"WARN: {failed} database(s) failed; {ok} succeeded. "
                    "Remote ERROR 1044 means that user cannot use that database—grant access on the host "
                    "or set SYNC_DATABASES to the schema(s) your user may write (e.g. cheradip_cheradip only)."
                )
            if not watch:
                break
            print(f"Next pass in {interval}s … (Ctrl+C to stop)\n")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).")
        return 0

    print("\nDone.")
    return 0


def _dotenv_dirs_for_cli() -> list[Path]:
    # .../bcheradip/cheradip/management/commands/mysql_db_sync.py -> project root
    project_root = Path(__file__).resolve().parents[3]
    scripts_dir = project_root / "scripts"
    out = [project_root, scripts_dir]
    cwd_scripts = Path.cwd() / "scripts"
    if cwd_scripts.is_dir() and cwd_scripts.resolve() not in {p.resolve() for p in out}:
        out.append(cwd_scripts)
    return out


def main_cli() -> None:
    """Argparse entry (``python -m cheradip.management.commands.mysql_db_sync``)."""
    dotenv_dirs = _dotenv_dirs_for_cli()
    load_dotenv(dotenv_dirs)

    ap = argparse.ArgumentParser(description="Sync MySQL/MariaDB databases local ↔ remote.")
    ap.add_argument(
        "--direction",
        choices=("local-to-remote", "remote-to-local"),
        default=env("SYNC_DIRECTION", "local-to-remote"),
        help="Copy direction (default: env SYNC_DIRECTION or local-to-remote).",
    )
    ap.add_argument(
        "--watch",
        action="store_true",
        default=env_bool("WATCH", False),
        help="Repeat sync every --interval seconds until Ctrl+C (env WATCH=1).",
    )
    ap.add_argument(
        "--interval",
        type=int,
        default=None,
        metavar="SEC",
        help="Seconds between watch passes (default: env WATCH_INTERVAL_SECONDS or 300).",
    )
    args = ap.parse_args()

    code = run_sync(
        direction=args.direction,
        watch=args.watch,
        interval=args.interval,
        dotenv_dirs=dotenv_dirs,
    )
    raise SystemExit(code)


class Command(BaseCommand):
    help = (
        "Full snapshot copy of MySQL/MariaDB databases (all tables + data) via mysqldump | mysql. "
        "--l2r: discover DBs on local, push to remote. --r2l: discover on remote, pull to local. "
        "Destination DBs are created if missing; existing destination tables are replaced from source."
    )

    def add_arguments(self, parser):
        direction = parser.add_mutually_exclusive_group(required=True)
        direction.add_argument(
            "--l2r",
            action="store_true",
            help="Local → remote: dump local, restore on remote.",
        )
        direction.add_argument(
            "--r2l",
            action="store_true",
            help="Remote → local: dump remote, restore on local.",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Repeat full sync every --interval seconds until Ctrl+C.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=None,
            metavar="SEC",
            help="Seconds between watch passes (default: WATCH_INTERVAL_SECONDS env or 300).",
        )

    def handle(self, *args, **options):
        direction = "local-to-remote" if options["l2r"] else "remote-to-local"
        base = Path(settings.BASE_DIR)
        dotenv_dirs = [base / "scripts", base]

        code = run_sync(
            direction=direction,
            watch=bool(options["watch"]),
            interval=options["interval"],
            dotenv_dirs=dotenv_dirs,
        )
        if code != 0:
            raise CommandError(f"Database sync exited with code {code}.")


if __name__ == "__main__":
    main_cli()
