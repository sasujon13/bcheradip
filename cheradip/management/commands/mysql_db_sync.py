"""
MySQL/MariaDB sync between local and remote (``mysqldump`` | ``mysql``).

**What ``--l2r`` / ``--r2l`` do**

- **``--l2r`` (local → remote):** Compares every base table and record in each
  selected local database using PyMySQL. Creates missing remote tables and
  inserts missing records only. Existing records, tables, views, triggers,
  routines, and events are never replaced. Missing databases are skipped with
  Linux database-creation commands; create them on the server and rerun.

- **``--r2l`` (remote → local):** Same flow with **remote** as the source and
  **local** as the destination.

**Databases on the destination**

For ``--r2l`` only, before each restore, the command runs
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

The above replacement rules apply to ``--r2l`` only. ``--l2r`` is insert-only:
primary/unique keys identify existing records even when their values differ.
Tables without usable unique keys use exact full-row comparison. Schema
differences are reported for manual migration; existing tables are not altered.
Duplicate-key conflicts are skipped, other insert errors fail that table.
Foreign keys remain enforced during inserts. Run while source writes are paused
for a consistent copy across related tables. Dry-run performs comparisons only.

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
- ``WATCH``, ``WATCH_INTERVAL_SECONDS`` — repeat the selected sync operation
- ``MYSQLDUMP_PATH``, ``MYSQL_PATH`` — overrides if clients not on ``PATH``
- ``MYSQL_SYNC_USE_TEMPFILE`` — ``1``/``true`` = dump to a temp file then import (default **on** on
  Windows; avoids broken-pipe ``errno 22``/``32`` when the remote server stops reading). ``0`` = pipe mode.
- ``MYSQL_SYNC_SKIP_REMOTE_ACCESS_CHECK`` — legacy option; ``--l2r`` now always checks each remote database.
- ``SSH_TUNNEL`` / ``SSH_HOST`` — when MySQL is only on the Linux server (not public), forward via SSH.
  ``SSH_USER``, ``SSH_PASSWORD`` (or key), ``SSH_PORT`` (22), ``SSH_LOCAL_PORT`` (13306),
  ``SSH_REMOTE_MYSQL_HOST`` (127.0.0.1), ``SSH_REMOTE_MYSQL_PORT`` (3306).
  Set ``SSH_TUNNEL_BACKEND=plink`` for legacy SSH servers no longer supported by Paramiko 5.
  PuTTY must already trust the server host key, or set ``SSH_HOST_KEY`` to its verified fingerprint.
  Requires ``pip install sshtunnel``. **Do not use ``cheradip.com``** for SSH/MySQL — that hostname is Cloudflare.
- ``SYNC_DATABASES`` — comma-separated allow list. Leave unset to use ``DEFAULT_SYNC_DATABASES`` in code
  (the eight project databases in ``DEFAULT_PROJECT_SYNC_DATABASES``).
  Set ``SYNC_DATABASES=*`` or ``SYNC_DATABASES=`` (empty) to sync **every** non-excluded database on the source.
  Use a narrower list when the remote user may only access specific schemas (avoids 1044 on ``CREATE DATABASE``).
- ``EXCLUDE_DATABASES`` — extra names to skip
- ``DRY_RUN`` — print only, no copy

**Invalid names (skipped automatically)**

Names that look like legacy data-directory junk (e.g. ``#mysql50#...`` or containing ``.corrupt``)
cannot be created on a normal server with ``CREATE DATABASE`` — they are omitted from the sync list.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pickle
import re
import shlex
import socket
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# ---------------------------------------------------------------------------
# mysql_db_sync defaults — edit here for quick sync without .env
# Environment variables (or dotenv) still override these when set.
# ---------------------------------------------------------------------------
DEFAULT_SYNC_REMOTE_HOST = "cheradip.com"
DEFAULT_SYNC_REMOTE_PORT = "3306"
DEFAULT_SYNC_REMOTE_USER = "sasha"
DEFAULT_SYNC_REMOTE_PASSWORD = ""

DEFAULT_SYNC_LOCAL_HOST = "127.0.0.1"
DEFAULT_SYNC_LOCAL_PORT = "3306"
DEFAULT_SYNC_LOCAL_USER = "root"
DEFAULT_SYNC_LOCAL_PASSWORD = ""  # empty = no password (typical XAMPP root)
# Project databases synced by default (--l2r / --r2l). Override with SYNC_DATABASES env var.
# Set SYNC_DATABASES=* or SYNC_DATABASES= (empty) to sync every non-excluded DB on the source instead.
DEFAULT_PROJECT_SYNC_DATABASES = (
    "cheradip_cheradip",
    "cheradip_hsc",
    "cheradip_honours",
    "cheradip_job",
    "ailanguagetutor",
    "extcheradip",
    "childcare",
    "ecommerce",
)
DEFAULT_SYNC_DATABASES = ",".join(DEFAULT_PROJECT_SYNC_DATABASES)
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
    but ``CREATE DATABASE`` rejects (ERROR 
    102 Incorrect database name).
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


class MissingRemoteDatabase(MySQLSyncError):
    """Remote database needs to be created by the server administrator."""


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


_CLOUDFLARE_HOSTNAMES = frozenset({"cheradip.com", "www.cheradip.com"})


def _ensure_paramiko_sshtunnel_compat() -> None:
    """sshtunnel 0.4.x imports paramiko.DSSKey, removed in paramiko 3.0+."""
    try:
        import paramiko  # type: ignore
    except ImportError:
        return
    if not hasattr(paramiko, "DSSKey"):
        paramiko.DSSKey = paramiko.RSAKey  # type: ignore[attr-defined]


@contextmanager
def _plink_mysql_tunnel(ssh_host: str, ssh_port: int, ssh_user: str,
                        ssh_password: str | None, ssh_pkey: str | None,
                        local_port: int, remote_mysql_host: str, remote_mysql_port: int):
    """Use PuTTY Plink for servers whose SSH algorithms Paramiko removed."""
    plink = env("PLINK_PATH") or shutil.which("plink")
    if not plink:
        raise MySQLSyncError(
            "SSH_TUNNEL_BACKEND=plink but plink was not found. Install PuTTY or set PLINK_PATH."
        )
    args = [plink, "-ssh", "-batch", "-N", "-noagent", "-noshare",
            "-P", str(ssh_port), "-l", ssh_user,
            "-L", f"127.0.0.1:{local_port}:{remote_mysql_host}:{remote_mysql_port}"]
    if env_bool("SSH_TUNNEL_DEBUG", False):
        args.insert(1, "-v")
    host_key = env("SSH_HOST_KEY")
    if host_key:
        args.extend(["-hostkey", host_key])
    password_file = None
    if ssh_pkey:
        args.extend(["-i", ssh_pkey])
    elif ssh_password:
        fd, password_file = tempfile.mkstemp(prefix="cheradip_ssh_", suffix=".txt")
        try:
            os.chmod(password_file, stat.S_IREAD | stat.S_IWRITE)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(ssh_password)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(password_file).unlink(missing_ok=True)
            raise
        args.extend(["-pwfile", password_file])
    args.append(ssh_host)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, text=True, creationflags=creationflags)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                detail = (process.stderr.read() if process.stderr else "").strip()
                raise MySQLSyncError("Plink SSH tunnel failed: " + (detail or "unknown error"))
            try:
                with socket.create_connection(("127.0.0.1", local_port), timeout=.4):
                    break
            except OSError:
                time.sleep(.2)
        else:
            raise MySQLSyncError("Timed out waiting for the Plink SSH tunnel to open.")
        if password_file:
            Path(password_file).unlink(missing_ok=True)
            password_file = None
        yield "127.0.0.1", str(local_port)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if password_file:
            Path(password_file).unlink(missing_ok=True)


def _warn_if_cloudflare_hostname(host: str) -> None:
    if host.strip().lower() in _CLOUDFLARE_HOSTNAMES:
        print(
            "WARN: cheradip.com / www.cheradip.com point to Cloudflare — not your Linux server.\n"
            "      MySQL and SSH cannot connect to that hostname (ERROR 2002 / timeout).\n"
            "      Set SSH_HOST to your server's real IP/hostname and SSH_TUNNEL=1 in .env.db-sync,\n"
            "      or run: ssh -N -L 13306:127.0.0.1:3306 USER@SERVER_IP\n"
            "      then REMOTE_HOST=127.0.0.1 REMOTE_PORT=13306"
        )


@contextmanager
def _ssh_mysql_tunnel(mysql_remote_host: str, mysql_remote_port: str):
    """
    Optional SSH port forward to reach MySQL on the Linux host (127.0.0.1:3306 there).
    Yields (effective_host, effective_port) for the mysql client.
    """
    ssh_host = (env("SSH_HOST") or "").strip()
    if not ssh_host and not env_bool("SSH_TUNNEL", False):
        yield mysql_remote_host, mysql_remote_port
        return

    if not ssh_host:
        raise MySQLSyncError("SSH_TUNNEL=1 but SSH_HOST is empty. Set SSH_HOST to your Linux server IP.")

    ssh_user = env("SSH_USER", "sasha") or "sasha"
    ssh_port = env_int("SSH_PORT", 22)
    ssh_password = env("SSH_PASSWORD")
    local_port = env_int("SSH_LOCAL_PORT", 13306)
    remote_mysql_host = env("SSH_REMOTE_MYSQL_HOST", "127.0.0.1") or "127.0.0.1"
    remote_mysql_port = env_int("SSH_REMOTE_MYSQL_PORT", int(mysql_remote_port or "3306"))
    ssh_pkey = env("SSH_PRIVATE_KEY")

    if (env("SSH_TUNNEL_BACKEND", "paramiko") or "paramiko").strip().lower() == "plink":
        print(
            f"SSH tunnel (Plink): {ssh_user}@{ssh_host}:{ssh_port} "
            f"-> 127.0.0.1:{local_port} -> {remote_mysql_host}:{remote_mysql_port}"
        )
        with _plink_mysql_tunnel(ssh_host, ssh_port, ssh_user, ssh_password, ssh_pkey,
                                 local_port, remote_mysql_host, remote_mysql_port) as endpoint:
            yield endpoint
        return

    try:
        _ensure_paramiko_sshtunnel_compat()
        from sshtunnel import SSHTunnelForwarder  # type: ignore
    except ImportError as exc:
        raise MySQLSyncError(
            "SSH tunnel requested but sshtunnel is not installed.\n"
            "  pip install sshtunnel paramiko\n"
            "Or start a tunnel manually in another terminal:\n"
            f"  ssh -N -L {local_port}:{remote_mysql_host}:{remote_mysql_port} "
            f"{ssh_user}@{ssh_host}\n"
            f"Then set REMOTE_HOST=127.0.0.1 REMOTE_PORT={local_port} (no SSH_TUNNEL)."
        ) from exc

    tunnel_kwargs: dict = {
        "ssh_address_or_host": (ssh_host, ssh_port),
        "ssh_username": ssh_user,
        "remote_bind_address": (remote_mysql_host, remote_mysql_port),
        "local_bind_address": ("127.0.0.1", local_port),
        "allow_agent": False,
        "host_pkey_directories": [],
    }
    if ssh_password:
        tunnel_kwargs["ssh_password"] = ssh_password
    if ssh_pkey:
        tunnel_kwargs["ssh_pkey"] = ssh_pkey

    print(
        f"SSH tunnel: {ssh_user}@{ssh_host}:{ssh_port} "
        f"-> 127.0.0.1:{local_port} -> {remote_mysql_host}:{remote_mysql_port}"
    )
    tunnel = SSHTunnelForwarder(**tunnel_kwargs)
    try:
        tunnel.start()
        if not tunnel.is_active:
            raise MySQLSyncError(f"SSH tunnel to {ssh_host} did not start.")
        yield "127.0.0.1", str(local_port)
    finally:
        tunnel.stop()


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


def print_remote_database_instructions(db: str, remote_user: str) -> None:
    ident = _quote_db_ident(db)
    sql = f"CREATE DATABASE IF NOT EXISTS {ident} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    print(f"    [MISSING DATABASE] {db}: run these commands on your remote Linux server:")
    print("      sudo mysql -e " + shlex.quote(sql))
    print("      sudo mysql -e " + shlex.quote(f"SHOW CREATE DATABASE {ident};"))
    print(f"    Then grant the existing MySQL account {remote_user!r} access to this database")
    print("    if needed, using its actual account Host value, and rerun --l2r.")
    print("    No remote database was created or replaced by this command.")


def _open_sync_connection(host, port, user, password, db):
    import pymysql

    return pymysql.connect(
        host=host, port=int(port), user=user, password=password or '',
        database=db, charset='utf8mb4', autocommit=False,
        connect_timeout=30, read_timeout=600, write_timeout=600,
    )


def _table_metadata(connection, table):
    """Get insertable columns and ordered primary/unique index columns."""
    with connection.cursor() as cursor:
        cursor.execute(f"SHOW FULL COLUMNS FROM {_quote_db_ident(table)}")
        fields = cursor.fetchall()
        # FULL COLUMNS: Field, Type, Collation, Null, Key, Default, Extra, ...
        columns = [row for row in fields if not re.search(
            r'\b(?:VIRTUAL|STORED) GENERATED\b', str(row[6]), re.I,
        )]
        cursor.execute(f"SHOW INDEX FROM {_quote_db_ident(table)}")
        indexes = {}
        expression_indexes = set()
        for row in cursor.fetchall():
            if row[1] == 0:
                if row[4]:
                    indexes.setdefault(row[2], []).append((row[3], row[4]))
                else:
                    expression_indexes.add(row[2])
        keys = [tuple(column for _, column in sorted(indexes[name]))
                for name in sorted(indexes, key=lambda name: (name != 'PRIMARY', name))
                if name not in expression_indexes]
    return columns, keys


def _row_identity(row, column_names, keys):
    """Use the first complete unique key; NULL keys need full-row comparison."""
    positions = {name: index for index, name in enumerate(column_names)}
    for key in keys:
        if not all(name in positions for name in key):
            continue
        values = tuple(row[positions[name]] for name in key)
        if all(value is not None for value in values):
            return ('key', key, values)
    return ('row', tuple(row))


def _identity_digest(identity):
    return hashlib.sha256(pickle.dumps(identity, protocol=4)).digest()


def _ordered_sync_tables(connection, db, tables):
    """Load parents before children; cycles are reported by enforced foreign keys."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME, REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_SCHEMA=%s "
            "AND REFERENCED_TABLE_NAME IS NOT NULL", (db, db),
        )
        dependencies = {table: set() for table in tables}
        for table, parent in cursor.fetchall():
            if table in dependencies and parent in dependencies and parent != table:
                dependencies[table].add(parent)
    ordered = []
    pending = set(tables)
    while pending:
        ready = sorted(table for table in pending if not dependencies[table] & pending)
        if not ready:
            print("    [WARN] Cyclic foreign keys: " + ', '.join(sorted(pending)) +
                  '. Inserts remain constrained; unresolved dependencies will be reported.')
            ordered.extend(sorted(pending))
            break
        ordered.extend(ready)
        pending.difference_update(ready)
    return ordered


def _copy_missing_rows(source, destination, table, *, dry=False, destination_exists=True):
    """Stream all records; disk-backed identity index bounds memory for large tables."""
    import pymysql

    source_fields, keys = _table_metadata(source, table)
    names = [field[0] for field in source_fields]
    if not names:
        raise MySQLSyncError(f'{table}: no insertable columns were found.')
    if destination_exists:
        destination_fields, _ = _table_metadata(destination, table)
        remote_fields = {field[0]: field for field in destination_fields}
        missing = set(names) - set(remote_fields)
        # Integer display widths vary between MySQL and MariaDB, not storage types.
        def normalized_type(value):
            return re.sub(r'\b(tinyint|smallint|mediumint|int|bigint)\(\d+\)',
                          r'\1', str(value).lower())
        changed = [field[0] for field in source_fields if field[0] in remote_fields and (
            normalized_type(field[1]) != normalized_type(remote_fields[field[0]][1])
            or field[2] != remote_fields[field[0]][2]
        )]
        if missing or changed:
            raise MySQLSyncError(
                f'{table}: schema mismatch; missing remote columns={sorted(missing)}, '
                f'incompatible types/collations={changed}. Apply the required remote '
                'schema migration and rerun; the existing table was not altered.'
            )
    columns = ', '.join(_quote_db_ident(name) for name in names)
    select_sql = f'SELECT {columns} FROM {_quote_db_ident(table)}'
    insert_sql = (f'INSERT INTO {_quote_db_ident(table)} ({columns}) VALUES (' +
                  ', '.join(['%s'] * len(names)) + ')')
    scanned = remote_count = inserted = existing = conflicts = 0
    with tempfile.TemporaryDirectory(prefix='cheradip_sync_compare_') as directory:
        index = sqlite3.connect(str(Path(directory) / 'identities.sqlite3'))
        try:
            index.execute('CREATE TABLE identities (digest BLOB PRIMARY KEY) WITHOUT ROWID')
            if destination_exists:
                with destination.cursor(pymysql.cursors.SSCursor) as cursor:
                    cursor.execute(select_sql)
                    while True:
                        rows = cursor.fetchmany(1000)
                        if not rows:
                            break
                        remote_count += len(rows)
                        index.executemany('INSERT OR IGNORE INTO identities VALUES (?)', [
                            (_identity_digest(_row_identity(row, names, keys)),) for row in rows
                        ])
                index.commit()
            with source.cursor(pymysql.cursors.SSCursor) as reader, destination.cursor() as writer:
                reader.execute(select_sql)
                while True:
                    rows = reader.fetchmany(500)
                    if not rows:
                        break
                    candidates = []
                    for row in rows:
                        scanned += 1
                        digest = _identity_digest(_row_identity(row, names, keys))
                        if index.execute('SELECT 1 FROM identities WHERE digest=?', (digest,)).fetchone():
                            existing += 1
                            continue
                        candidates.append(row)
                        # Also prevent identical keyless local rows being sent twice in a batch.
                        index.execute('INSERT OR IGNORE INTO identities VALUES (?)', (digest,))
                    if candidates and not dry:
                        writer.execute('SAVEPOINT sync_insert_batch')
                        try:
                            writer.executemany(insert_sql, candidates)
                            inserted += len(candidates)
                        except pymysql.IntegrityError as error:
                            # A conflicting row must not prevent other missing rows in this batch.
                            writer.execute('ROLLBACK TO SAVEPOINT sync_insert_batch')
                            if error.args[0] != 1062:
                                raise
                            for row in candidates:
                                try:
                                    writer.execute(insert_sql, row)
                                    inserted += 1
                                except pymysql.IntegrityError as conflict:
                                    if conflict.args[0] != 1062:
                                        raise
                                    conflicts += 1
                        writer.execute('RELEASE SAVEPOINT sync_insert_batch')
                        destination.commit()
                    elif dry:
                        inserted += len(candidates)
                    index.commit()
                    if scanned % 10000 == 0:
                        print(f'      {table}: {scanned:,} scanned, {inserted:,} missing records processed')
            if not dry:
                destination.commit()
        except Exception:
            destination.rollback()
            raise
        finally:
            index.close()
    print(f'      {table}: local={scanned:,}, remote scanned={remote_count:,}, '
          f'{"would insert" if dry else "inserted"}={inserted:,}, '
          f'existing unchanged={existing:,}, duplicate-key conflicts skipped={conflicts:,}')


def sync_missing_to_remote(*, source_host, source_port, source_user, source_password,
                           dest_host, dest_port, dest_user, dest_password, db, dry, **unused):
    """Insert-only local → remote path, completely separate from snapshot restore."""
    import pymysql

    try:
        destination = _open_sync_connection(dest_host, dest_port, dest_user, dest_password, db)
    except pymysql.MySQLError as error:
        if error.args[0] == 1049:
            print_remote_database_instructions(db, dest_user)
            raise MissingRemoteDatabase(f'{db}: missing on remote; create it using the commands above.') from error
        raise MySQLSyncError(f'{db}: remote connection/access failed: {error}') from error
    try:
        source = _open_sync_connection(source_host, source_port, source_user, source_password, db)
        try:
            with source.cursor() as cursor:
                cursor.execute('SHOW FULL TABLES')
                objects = cursor.fetchall()
                tables = sorted(row[0] for row in objects if row[1] == 'BASE TABLE')
                views = [row[0] for row in objects if row[1] != 'BASE TABLE']
            with destination.cursor() as cursor:
                cursor.execute('SHOW FULL TABLES')
                remote_objects = dict(cursor.fetchall())
                cursor.execute('SET SESSION FOREIGN_KEY_CHECKS=1')
                # Strict inserts prevent silent data conversion in permissive servers.
                cursor.execute("SET SESSION sql_mode=CONCAT_WS(',', @@sql_mode, 'STRICT_ALL_TABLES', 'NO_AUTO_VALUE_ON_ZERO')")
            print(f'    Comparing all {len(tables)} local tables; {len(remote_objects)} remote objects.')
            if views:
                print('    Views are not data tables and are preserved: ' + ', '.join(views))
            failed = []
            created = set()
            # Create the missing structure first so inter-table references can resolve.
            for table in tables:
                if table in remote_objects:
                    continue
                print(f'    {"[DRY_RUN] Would create" if dry else "Creating"} missing table: {db}.{table}')
                if dry:
                    continue
                try:
                    with source.cursor() as reader, destination.cursor() as writer:
                        reader.execute(f'SHOW CREATE TABLE {_quote_db_ident(table)}')
                        ddl = reader.fetchone()[1]
                        writer.execute('SET SESSION FOREIGN_KEY_CHECKS=0')
                        try:
                            writer.execute(ddl)
                        finally:
                            writer.execute('SET SESSION FOREIGN_KEY_CHECKS=1')
                    destination.commit()
                    created.add(table)
                    remote_objects[table] = 'BASE TABLE'
                except pymysql.MySQLError as error:
                    failed.append(table)
                    print(f'    [FAIL] {table}: could not create table: {error}')
            for number, table in enumerate(_ordered_sync_tables(source, db, tables), 1):
                print(f'    [{number}/{len(tables)} tables] Comparing {db}.{table}')
                if table in failed:
                    continue
                if table in remote_objects and remote_objects[table] != 'BASE TABLE':
                    failed.append(table)
                    print(f'    [FAIL] {table}: remote object is a view; left unchanged.')
                    continue
                try:
                    _copy_missing_rows(source, destination, table, dry=dry,
                                       destination_exists=table in remote_objects)
                except (MySQLSyncError, pymysql.MySQLError) as error:
                    failed.append(table)
                    print(f'    [FAIL] {table}: {error}')
                    if _is_network_error_message(str(error)):
                        raise MySQLSyncError(str(error)) from error
            remote_only = sorted(set(remote_objects) - set(tables) - set(views))
            if remote_only:
                print('    Remote-only objects retained: ' + ', '.join(remote_only))
            print(f'    Missing tables created={len(created)}; table failures={len(failed)}.')
            if failed:
                raise MySQLSyncError(f'{db}: incomplete comparison/import for tables: ' + ', '.join(failed))
        finally:
            source.close()
    except pymysql.MySQLError as error:
        raise MySQLSyncError(f'{db}: comparison/import failed: {error}') from error
    finally:
        destination.close()


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
                "(hosting often allows only one DB name). Use SYNC_DATABASES=cheradip_cheradip,ailanguagetutor or "
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
    if only:
        missing = sorted(only - set(all_names))
        if missing:
            print(
                "WARN: SYNC_DATABASES name(s) not found on source (skipped until created there):\n  "
                + ", ".join(missing)
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
                sync_function = sync_missing_to_remote if direction == 'local-to-remote' else sync_one_database
                sync_function(
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
            except MissingRemoteDatabase as error:
                failed += 1
                print(f"    [SKIPPED] {error}")
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

    dry = env_bool("DRY_RUN", False)
    sync_raw = (env("SYNC_DATABASES", DEFAULT_SYNC_DATABASES) or "").strip()
    if sync_raw in ("*", ""):
        only: set[str] = set()
    else:
        only = parse_csv(sync_raw)
    extra_exclude = parse_csv(env("EXCLUDE_DATABASES"))
    direction = direction.strip().lower()

    if not remote_host or not remote_user or remote_password is None:
        print(
            "ERROR: Remote host, user, and password are missing. "
            "Set DEFAULT_SYNC_* in mysql_db_sync.py or REMOTE_* in the environment / .env.db-sync."
        )
        return 2

    _warn_if_cloudflare_hostname(remote_host)

    mysqldump = find_client("mysqldump", env("MYSQLDUMP_PATH"))
    mysql = find_client("mysql", env("MYSQL_PATH"))
    if not mysql or (direction == 'remote-to-local' and not mysqldump):
        print(
            "ERROR: mysqldump and/or mysql not found. Set MYSQLDUMP_PATH / MYSQL_PATH\n"
            "  (e.g. C:\\xampp\\mysql\\bin\\mysqldump.exe)."
        )
        return 2

    try:
        with _ssh_mysql_tunnel(remote_host, remote_port) as (remote_host, remote_port):
            return _run_sync_connected(
                direction=direction,
                watch=watch,
                interval=interval,
                remote_host=remote_host,
                remote_port=remote_port,
                remote_user=remote_user,
                remote_password=remote_password,
                local_host=local_host,
                local_port=local_port,
                local_user=local_user,
                local_password=local_password,
                mysqldump=mysqldump or '',
                mysql=mysql,
                dry=dry,
                only=only,
                extra_exclude=extra_exclude,
            )
    except MySQLSyncError as e:
        print("ERROR:", e)
        return 1


def _run_sync_connected(
    *,
    direction: str,
    watch: bool,
    interval: int,
    remote_host: str,
    remote_port: str,
    remote_user: str,
    remote_password: str | None,
    local_host: str,
    local_port: str,
    local_user: str,
    local_password: str,
    mysqldump: str,
    mysql: str,
    dry: bool,
    only: set[str],
    extra_exclude: set[str],
) -> int:
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
    if direction == 'local-to-remote':
        print('Mode: compare every table and record; create missing tables; insert missing rows only.')
        print('Missing remote databases need manual creation. Existing remote data is never overwritten.')
    elif _use_tempfile_for_sync():
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
                    "or set SYNC_DATABASES to the schema(s) your user may write (e.g. cheradip_cheradip,ailanguagetutor)."
                )
            if not watch:
                break
            print(f"Next pass in {interval}s … (Ctrl+C to stop)\n")
            time.sleep(interval)
            to_sync = resolve_databases(mysql, list_host, list_port, list_user, list_pw, only, extra_exclude)
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).")
        return 0

    print("\nDone.")
    return 1 if failed else 0


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
        "--l2r: compare local/remote tables and rows, create missing tables and insert missing rows only; "
        "print Linux creation commands for missing remote databases. "
        "--r2l: full snapshot restore; existing local tables are replaced from remote."
    )

    def add_arguments(self, parser):
        direction = parser.add_mutually_exclusive_group(required=True)
        direction.add_argument(
            "--l2r",
            action="store_true",
            help="Local → remote: create missing tables and insert only missing rows (no updates/deletes).",
        )
        direction.add_argument(
            "--r2l",
            action="store_true",
            help="Remote → local: dump remote, restore on local.",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Repeat the selected sync operation every --interval seconds until Ctrl+C.",
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
