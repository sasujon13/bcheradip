# Django management command: python manage.py check_migration_tables
# Compares actual DB table names with what your models expect (db_table).
# Run from bcheradip: python manage.py check_migration_tables

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = (
        "List table names in the database. Models are aligned with cheradip_* "
        "table names (e.g. cheradip_orders, cheradip_chapters)."
    )

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            if connection.vendor == "mysql":
                cursor.execute("SHOW TABLES")
                rows = cursor.fetchall()
                # MySQL returns (table_name,) per row; key is often like 'Tables_in_cheradip'
                tables = [row[0] for row in rows]
            elif connection.vendor == "sqlite":
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]
            else:
                self.stdout.write(
                    self.style.WARNING("Only MySQL and SQLite are supported.")
                )
                return

        tables.sort()
        self.stdout.write(
            self.style.SUCCESS(
                f"Tables in DB ({connection.settings_dict['NAME']}) ({len(tables)} total):"
            )
        )
        for t in tables:
            self.stdout.write(f"  {t}")

        cheradip_tables = [t for t in tables if t.startswith("cheradip_")]
        self.stdout.write("")
        self.stdout.write(
            self.style.NOTICE(
                f"Tables with cheradip_ prefix: {len(cheradip_tables)} (models expect these)."
            )
        )
