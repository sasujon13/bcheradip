#!/usr/bin/env python3
"""Create MySQL database (if missing) and tables + seed data."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import pymysql
from sqlalchemy import create_engine, text

from app.config import settings
from app.seed import init_database, init_ext_database


def ensure_database_exists(database_url: str, fallback_name: str) -> None:
    parsed = urlparse(database_url.replace("mysql+pymysql://", "mysql://"))
    db_name = (parsed.path or f"/{fallback_name}").lstrip("/").split("?")[0]
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    user = parsed.username or "root"
    password = parsed.password or ""

    conn = pymysql.connect(host=host, port=port, user=user, password=password)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print(f"Database `{db_name}` ready.")
    finally:
        conn.close()


def main() -> int:
    try:
        ensure_database_exists(settings.database_url, "ailanguagetutor")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        init_database()
        print("Main DB tables created and seed data loaded.")

        ensure_database_exists(settings.ext_database_url, "extcheradip")
        ext_engine = create_engine(settings.ext_database_url, pool_pre_ping=True)
        with ext_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        init_ext_database()
        print("Extension DB (extcheradip) tables created and seed data loaded.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Start XAMPP MySQL, then run again.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
