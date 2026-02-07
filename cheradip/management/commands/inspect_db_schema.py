# Dump actual DB table names and columns for alignment with models.
# Run: python manage.py inspect_db_schema

import json
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Dump actual database table names and their columns (for aligning models)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            type=str,
            default="",
            help="Write JSON to this file (e.g. db_schema.json).",
        )

    def handle(self, *args, **options):
        out = {}
        with connection.cursor() as cursor:
            if connection.vendor != "mysql":
                self.stdout.write(self.style.ERROR("Only MySQL supported for this command."))
                return
            db_name = connection.settings_dict["NAME"]
            cursor.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s
                AND TABLE_NAME NOT LIKE 'django_%%'
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                [db_name],
            )
            rows = cursor.fetchall()
            for table_name, column_name, data_type, is_nullable, column_default in rows:
                if table_name not in out:
                    out[table_name] = []
                out[table_name].append(
                    {
                        "column": column_name,
                        "data_type": data_type,
                        "nullable": is_nullable == "YES",
                        "default": column_default,
                    }
                )

        if options["json"]:
            with open(options["json"], "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2)
            self.stdout.write(self.style.SUCCESS(f"Wrote {options['json']}"))
        else:
            for table in sorted(out.keys()):
                self.stdout.write(f"\n{table}")
                for c in out[table]:
                    self.stdout.write(f"  - {c['column']} ({c['data_type']})")
        self.stdout.write(f"\nTables: {list(sorted(out.keys()))}")
        return out
