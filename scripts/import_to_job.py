"""
Import SQL dumps (cheradip_banbeis, cheradip_institutes, etc.) into cheradip_job database.
Tables must already exist in cheradip_job; only INSERTs are run.
Strips CREATE TABLE and ALTER TABLE so no "table exists" or "duplicate key" DDL errors.
Uses: root, no password (or set MYSQL_PASSWORD). XAMPP mysql path or mysql in PATH.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(r"C:\Users\sasha\Desktop\database")
# SQL files to import into cheradip_job (table name = filename without .sql)
JOB_SQL_FILES = [
    "cheradip_banbeis.sql",
    "cheradip_institutes.sql",
    "cheradip_merit5.sql",
    "cheradip_merit6.sql",
    "cheradip_merit7.sql",
    "cheradip_recommend5.sql",
    "cheradip_recommend6.sql",
    "cheradip_vacancy5.sql",
    "cheradip_vacancy6.sql",
    "cheradip_vacancy7.sql",
    "cheradip_token.sql"
]
DB_NAME = "cheradip_job"
USER = os.environ.get("MYSQL_USER", "root")
PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
CHARSET = "utf8mb4"
MYSQL_PATHS = ["mysql", r"C:\xampp\mysql\bin\mysql.exe"]


def find_mysql():
    for p in MYSQL_PATHS:
        try:
            if subprocess.run([p, "--version"], capture_output=True, timeout=5).returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def strip_for_data_only(content: str) -> str:
    """Remove CREATE TABLE and all ALTER TABLE so only SET/INSERT/COMMIT remain."""
    # CREATE TABLE ... ; (single statement, may span many lines)
    content = re.sub(
        r"CREATE\s+TABLE\s+`[^`]+`\s*\(.*?\n\)\s*ENGINE=.*?;",
        "-- CREATE TABLE removed (table already exists)\n",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # ALTER TABLE ... ADD PRIMARY KEY / ADD KEY / ADD CONSTRAINT
    content = re.sub(
        r"ALTER\s+TABLE\s+`[^`]+`\s+ADD\s+[^;]*;",
        "-- ALTER TABLE ADD removed\n",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # ALTER TABLE ... MODIFY ... AUTO_INCREMENT
    content = re.sub(
        r"ALTER\s+TABLE\s+`[^`]+`\s+MODIFY\s+[^;]*;",
        "-- ALTER TABLE MODIFY removed\n",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # INSERT -> INSERT IGNORE to skip duplicates if re-run
    content = re.sub(r"\bINSERT\s+INTO\b", "INSERT IGNORE INTO", content, flags=re.IGNORECASE)
    return content


def run_sql(mysql_exe: str, sql: str) -> tuple[int, str]:
    cmd = [
        mysql_exe, "-u", USER,
        f"--default-character-set={CHARSET}",
        DB_NAME,
    ]
    if PASSWORD:
        cmd.insert(-1, f"--password={PASSWORD}")
    p = subprocess.run(
        cmd,
        input=sql.encode("utf-8"),
        capture_output=True,
        timeout=600,
    )
    err = (p.stderr or b"").decode("utf-8", errors="replace")
    return p.returncode, err


def main():
    if not SOURCE_DIR.exists():
        print(f"ERROR: Directory not found: {SOURCE_DIR}")
        sys.exit(1)
    mysql_exe = find_mysql()
    if not mysql_exe:
        print("ERROR: mysql not found. Add XAMPP mysql to PATH or set MYSQL_PATHS.")
        sys.exit(1)
    print(f"Using: {mysql_exe}")
    print(f"Database: {DB_NAME} (user: {USER})")
    failed = []
    for filename in JOB_SQL_FILES:
        path = SOURCE_DIR / filename
        if not path.exists():
            print(f"SKIP (not found): {filename}")
            continue
        table_name = path.stem  # e.g. cheradip_banbeis
        print(f"Importing: {filename} -> {table_name} ...", end=" ", flush=True)
        raw = path.read_text(encoding="utf-8", errors="replace")
        sql = strip_for_data_only(raw)
        code, err = run_sql(mysql_exe, sql)
        if code == 0:
            print("OK")
        else:
            print(f"FAILED (exit {code})")
            if err.strip():
                print(err.strip()[:500])
            failed.append(filename)
    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
