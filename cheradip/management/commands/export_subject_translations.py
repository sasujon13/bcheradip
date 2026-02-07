# -*- coding: utf-8 -*-
"""
Export cheradip_subject_translated to CSV or SQL as UTF-8 so Bengali/Unicode
stays correct when downloading or opening in Excel/SQL tools.

CSV: uses utf-8-sig (UTF-8 with BOM) so Excel opens Bengali correctly.
SQL: raw UTF-8; use mysqldump --default-character-set=utf8mb4 for full DB.

Run: python manage.py export_subject_translations
     python manage.py export_subject_translations --format sql --out translations.sql
     python manage.py export_subject_translations --lang bn --out bn_translations.csv

For full DB SQL dump with Bengali intact, use:
  mysqldump --default-character-set=utf8mb4 -u USER -p DATABASE > dump.sql
"""
import csv
import os
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Export subject translations to CSV or SQL in UTF-8 (Bengali/Unicode preserved)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format', '-f',
            choices=['csv', 'sql'],
            default='csv',
            help='Output format: csv (default) or sql',
        )
        parser.add_argument(
            '--out', '-o',
            default='subject_translations.csv',
            help='Output file path (default: subject_translations.csv)',
        )
        parser.add_argument(
            '--lang',
            default=None,
            help='Filter by language_code (e.g. bn). Omit for all.',
        )

    def handle(self, *args, **options):
        fmt = options.get('format', 'csv')
        out_path = options.get('out', 'subject_translations.csv')
        lang_filter = options.get('lang')

        with connection.cursor() as cur:
            cur.execute("SET NAMES 'utf8mb4'")
            where = "WHERE st.language_code = %s" if lang_filter else ""
            params = [lang_filter] if lang_filter else []
            cur.execute(f"""
                SELECT st.subject_id, st.language_code, st.level, st.subject_name, st.`groups`, st.created_at, st.updated_at,
                       s.country_id
                FROM cheradip_subject_translated st
                LEFT JOIN cheradip_subject s ON s.id = st.subject_id
                {where}
                ORDER BY st.language_code, st.subject_id
            """, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]

        if fmt == 'csv':
            self._write_csv(out_path, cols, rows)
        else:
            self._write_sql(out_path, cols, rows)

        self.stdout.write(self.style.SUCCESS(f'Exported {len(rows)} rows to {out_path} (UTF-8, Bengali preserved)'))

    def _write_csv(self, path, cols, rows):
        # utf-8-sig = UTF-8 with BOM so Excel opens Bengali correctly
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in rows:
                w.writerow(self._row_str(row))

    def _write_sql(self, path, cols, rows):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("-- UTF-8; Bengali/Unicode preserved. Import with mysql --default-character-set=utf8mb4\n")
            f.write("SET NAMES 'utf8mb4';\n\n")
            if rows:
                col_list = ', '.join(f'`{c}`' for c in cols)
                f.write("INSERT INTO cheradip_subject_translated (%s) VALUES\n" % col_list)
                lines = []
                for row in rows:
                    vals = ', '.join(self._sql_val(x) for x in row)
                    lines.append('  (%s)' % vals)
                f.write(',\n'.join(lines))
                f.write(';\n')

    def _row_str(self, row):
        return ['' if x is None else str(x) for x in row]

    def _sql_val(self, x):
        if x is None:
            return 'NULL'
        s = str(x).replace('\\', '\\\\').replace('\r', '\\r').replace('\n', '\\n').replace("'", "\\'")
        return "'%s'" % s
