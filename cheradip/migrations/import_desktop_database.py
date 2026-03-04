"""
Import SQL dumps from C:\\Users\\sasha\\Desktop\\database into cheradip_cheradip.
Strips CREATE TABLE and ALTER TABLE so only SET/INSERT/COMMIT run (no "table exists" or "multiple primary key" errors).
Uses: root, no password, database cheradip_cheradip. XAMPP mysql path or mysql in PATH.
"""
import re
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(r"C:\Users\sasha\Desktop\database")
DB_NAME = "cheradip_cheradip"
USER = "root"
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


def strip_create_and_alter(content: str) -> str:
    """Remove CREATE TABLE and ALTER TABLE ... ADD ... blocks so only INSERT/SET/COMMIT remain."""
    # Remove CREATE TABLE `name` ( ... ) ENGINE=...; (match up to newline + closing paren + ENGINE)
    content = re.sub(
        r"CREATE\s+TABLE\s+`[^`]+`\s*\(.*?\n\)\s*ENGINE=.*?;",
        "-- CREATE TABLE removed (table already exists)\n",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove ALTER TABLE `name` ADD PRIMARY KEY / ADD KEY ... ;
    content = re.sub(
        r"ALTER\s+TABLE\s+`[^`]+`\s+ADD[^;]*;",
        "-- ALTER TABLE removed (indexes already exist)\n",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # So re-runs don't fail on duplicate keys
    content = re.sub(r"\bINSERT\s+INTO\b", "INSERT IGNORE INTO", content, flags=re.IGNORECASE)
    return content


def run_sql(mysql_exe: str, sql: str) -> tuple[int, str]:
    p = subprocess.run(
        [mysql_exe, "-u", USER, f"--default-character-set={CHARSET}", DB_NAME],
        input=sql.encode("utf-8"),
        capture_output=True,
        timeout=600,
    )
    err = (p.stderr or b"").decode("utf-8", errors="replace")
    return p.returncode, err


def main():
    if not SOURCE_DIR.exists():
        print(f"ERROR: Source folder not found: {SOURCE_DIR}")
        sys.exit(1)
    mysql_exe = find_mysql()
    if not mysql_exe:
        print("ERROR: mysql not found. Add XAMPP mysql to PATH or set MYSQL_PATHS.")
        sys.exit(1)
    print(f"Using: {mysql_exe}")
    print(f"Importing into {DB_NAME} (user: {USER})")
    files = [
        "cheradip_country.sql",
        "cheradip_location.sql",
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
        "cheradip_subject_translated.sql",
        "cheradip_token.sql",
    ]
    for f in files:
        path = SOURCE_DIR / f
        if not path.exists():
            print(f"SKIP (not found): {f}")
            continue
        print(f"Importing: {f} ...", end=" ", flush=True)
        raw = path.read_text(encoding="utf-8", errors="replace")
        sql = strip_create_and_alter(raw)
        code, err = run_sql(mysql_exe, sql)
        if code == 0:
            print("OK")
        else:
            print(f"exit {code}")
            if err.strip():
                print(err.strip()[:500])
    # Copy from dump table names to Django table names
    copies = [
        (
            "cheradip_token -> tokens",
            "INSERT IGNORE INTO tokens (id, Token, Counter, Status, purpose, expires_at, created_at, updated_at) "
            "SELECT id, CAST(Token AS UNSIGNED), COALESCE(CAST(Counter AS CHAR), ''), Status, NULL, NULL, NOW(), NOW() FROM cheradip_token;",
        ),
        (
            "cheradip_merit -> cheradip_merit7",
            "INSERT IGNORE INTO cheradip_merit7 (id, Code, Name, Batch, Roll, Mark, Rank, SL, Subject) "
            "SELECT id, Code, Name, Batch, Roll, Mark, Rank, SL, Subject FROM cheradip_merit;",
        ),
        (
            "cheradip_vacancy -> cheradip_vacancy7",
            "INSERT IGNORE INTO cheradip_vacancy7 (VPID, EIIN, Name, District, Thana, Designation, Subject, Vacancy, Type, Status) "
            "SELECT VPID, EIIN, Name, District, Thana, Designation, Subject, Vacancy, Type, Status FROM cheradip_vacancy;",
        ),
    ]
    print("Copying data to Django table names ...")
    for label, sql in copies:
        print(f"  {label} ...", end=" ", flush=True)
        code, err = run_sql(mysql_exe, sql)
        if code == 0:
            print("OK")
        else:
            print(f"exit {code}")
    print("Done.")


if __name__ == "__main__":
    main()
