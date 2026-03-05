"""
Import CSV into a subject question table (e.g. cheradip_higher_secon_11_12_information_and_communication_techno).
Table has 18 data columns (id is AUTO_INCREMENT): subject, chapter_no, chapter, topic, question,
option_1, option_2, option_3, option_4, answer, explanation, explanation2, explanation3, type, level, subsource,
created_at, updated_at, updated_by.

If your CSV has a different layout (e.g. more columns or merged fields), use --columns to map by 0-based column index.
Example: --columns=0,1,...,17 means CSV columns map to the 18 table fields in order.
Use --no-header if the first row is data, not headers. Omit or leave empty created_at/updated_at/updated_by to leave NULL.
"""
import csv
import re
from django.core.management.base import BaseCommand
from django.db import connection

# Column order for INSERT (no id)
COLUMNS = [
    'subject', 'chapter_no', 'chapter', 'topic', 'question',
    'option_1', 'option_2', 'option_3', 'option_4', 'answer',
    'explanation', 'explanation2', 'explanation3', 'type', 'level', 'subsource',
    'created_at', 'updated_at', 'updated_by'
]


def _allowed_table(name):
    return isinstance(name, str) and bool(re.match(r'^cheradip_[a-z0-9_]+$', name.strip().lower()))


def _safe(val, max_len=None):
    if val is None:
        return None
    s = (val if isinstance(val, str) else str(val)).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        return s[:max_len]
    return s


class Command(BaseCommand):
    help = 'Import CSV into a subject question table. Use --columns to map CSV columns by index (0-based).'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='Path to CSV file')
        parser.add_argument('table_name', help='Target table (e.g. cheradip_higher_secon_11_12_information_and_communication_techno)')
        parser.add_argument(
            '--columns',
            type=str,
            default=None,
            help='Comma-separated 0-based column indices for the 18 fields in order: subject,chapter_no,chapter,topic,question,option_1..4,answer,explanation,explanation2,explanation3,type,level,subsource,created_at,updated_at,updated_by'
        )
        parser.add_argument('--no-header', action='store_true', help='First row is data, not headers')
        parser.add_argument('--truncate', action='store_true', help='Truncate table before import')
        parser.add_argument('--encoding', default='utf-8-sig', help='CSV encoding (default: utf-8-sig)')

    def handle(self, *args, **options):
        path = options['csv_path']
        table = options['table_name'].strip()
        if not _allowed_table(table):
            self.stdout.write(self.style.ERROR('Invalid table_name. Must match cheradip_[a-z0-9_]+'))
            return

        col_indices = None
        if options['columns']:
            parts = [p.strip() for p in options['columns'].split(',')]
            if len(parts) != 18:
                self.stdout.write(self.style.ERROR('--columns must have exactly 18 comma-separated indices.'))
                return
            try:
                col_indices = [int(p) for p in parts]
            except ValueError:
                self.stdout.write(self.style.ERROR('--columns must be integers.'))
                return

        try:
            with open(path, 'r', encoding=options['encoding'], newline='', errors='replace') as f:
                reader = csv.reader(f)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'File not found: {path}'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return

        if not rows:
            self.stdout.write('CSV is empty.')
            return

        if not options['no_header'] and not col_indices:
            # Assume first row is header; skip it and use column count to infer mapping
            header = rows[0]
            rows = rows[1:]
            if len(header) < 18:
                self.stdout.write(self.style.ERROR(
                    f'CSV has {len(header)} columns; need at least 18. Use --columns to map your columns to the 18 fields.'
                ))
                return
            # By default use first 18 columns in order
            col_indices = list(range(18))

        if col_indices is None:
            # No header and no --columns: use first 18 columns
            col_indices = list(range(18))

        placeholders = ', '.join(['%s'] * 18)
        cols_sql = ', '.join(COLUMNS)
        sql = f"INSERT INTO `{table}` ({cols_sql}) VALUES ({placeholders})"

        with connection.cursor() as cur:
            if options['truncate']:
                cur.execute(f"TRUNCATE TABLE `{table}`")
                self.stdout.write(f'Truncated {table}.')

            inserted = 0
            max_lens = {
                'subject': 255, 'chapter_no': 50, 'chapter': 255, 'topic': 255,
                'option_1': 500, 'option_2': 500, 'option_3': 500, 'option_4': 500,
                'answer': 500, 'type': 100, 'level': 100, 'subsource': 255, 'updated_by': 255
            }
            for i, row in enumerate(rows):
                if len(row) <= max(col_indices):
                    self.stdout.write(self.style.WARNING(f'Row {i+1}: not enough columns, skipped.'))
                    continue
                try:
                    values = []
                    for c, col_name in enumerate(COLUMNS):
                        idx = col_indices[c]
                        val = row[idx] if idx < len(row) else ''
                        if col_name in max_lens:
                            val = _safe(val, max_lens[col_name])
                        else:
                            val = _safe(val)
                        values.append(val)
                    cur.execute(sql, values)
                    inserted += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Row {i+1} skip: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Imported {inserted} rows into {table}.'))
