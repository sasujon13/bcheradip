"""
Remove Draft.js (and similar) JSON from text columns in cheradip_honours and cheradip_hsc.
Replaces JSON with plain text only (blocks[].text joined by newline).

Processes all tables in both databases. For each table, checks columns: question,
option_1, option_2, option_3, option_4, answer, explanation, explanation2, explanation3.
If a cell value looks like JSON (e.g. starts with '{' and contains "blocks"), extracts
plain text and updates the row.

Usage:
  python manage.py ensure_json_removed
  python manage.py ensure_json_removed --dry-run
  python manage.py ensure_json_removed --db honours
  python manage.py ensure_json_removed --db hsc
"""
import ast
import json
import logging
from django.core.management.base import BaseCommand
from django.db import connections

logger = logging.getLogger(__name__)

# Columns that may contain editor JSON (we only process these if they exist)
TEXT_COLUMNS = [
    'question', 'option_1', 'option_2', 'option_3', 'option_4',
    'answer', 'explanation', 'explanation2', 'explanation3',
]


def extract_plain_text_from_editor_json(value):
    """
    If value is Draft.js-style JSON (has "blocks" array), return plain text.
    Otherwise return value unchanged (string or None).
    Accepts standard JSON (double quotes) or Python literal (single quotes).
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='replace')
    if isinstance(value, dict):
        obj = value
    elif isinstance(value, str):
        s = value.strip()
        if not s or not s.startswith('{') or 'blocks' not in s:
            return value
        try:
            obj = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            try:
                if s.startswith('{'):
                    obj = ast.literal_eval(value)
                else:
                    return value
            except (ValueError, SyntaxError):
                return value
    else:
        return value
    if not isinstance(obj, dict):
        return value
    blocks = obj.get('blocks') or []
    texts = []
    for block in blocks:
        if isinstance(block, dict):
            t = block.get('text', '')
            if t is not None:
                texts.append(str(t))
    return '\n'.join(texts) if texts else (value if isinstance(value, str) else '')


def get_tables(cursor, db_name):
    """Return list of table names in the database."""
    cursor.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
        [db_name]
    )
    return [row[0] for row in cursor.fetchall()]


def get_primary_key_column(cursor, db_name, table_name):
    """Return the primary key column name (e.g. qid or id)."""
    cursor.execute(
        """SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
           WHERE table_schema = %s AND table_name = %s AND constraint_name = 'PRIMARY'
           ORDER BY ORDINAL_POSITION LIMIT 1""",
        [db_name, table_name]
    )
    row = cursor.fetchone()
    return row[0] if row else None


def get_existing_text_columns(cursor, db_name, table_name):
    """Return subset of TEXT_COLUMNS that exist in this table."""
    placeholders = ', '.join(['%s'] * len(TEXT_COLUMNS))
    cursor.execute(
        f"""SELECT column_name FROM information_schema.columns
           WHERE table_schema = %s AND table_name = %s AND column_name IN ({placeholders})
           AND data_type IN ('varchar', 'text', 'longtext', 'mediumtext')""",
        [db_name, table_name] + TEXT_COLUMNS
    )
    return [row[0] for row in cursor.fetchall()]


def process_database(alias, dry_run=False):
    """
    Process all tables in the given database alias (e.g. 'honours', 'hsc').
    Returns (tables_processed, rows_updated).
    """
    if alias not in connections:
        logger.warning('Database alias %s not configured', alias)
        return 0, 0
    conn = connections[alias]
    db_name = conn.settings_dict.get('NAME', '')
    tables_processed = 0
    total_rows_updated = 0
    with conn.cursor() as cur:
        tables = get_tables(cur, db_name)
        for table_name in tables:
            pk_col = get_primary_key_column(cur, db_name, table_name)
            if not pk_col:
                continue
            cols = get_existing_text_columns(cur, db_name, table_name)
            if not cols:
                continue
            tables_processed += 1
            # SELECT pk, col1, col2, ...
            safe_table = table_name.replace('`', '``')
            cols_quoted = ', '.join(f'`{c}`' for c in cols)
            select_sql = f"SELECT `{pk_col.replace('`', '``')}`, {cols_quoted} FROM `{safe_table}`"
            cur.execute(select_sql)
            rows = cur.fetchall()
            pk_index = 0
            col_indexes = list(range(1, 1 + len(cols)))
            for row in rows:
                pk_val = row[pk_index]
                updates = {}
                for i, col in enumerate(cols):
                    val = row[col_indexes[i]]
                    new_val = extract_plain_text_from_editor_json(val)
                    if new_val != val:
                        updates[col] = new_val
                if not updates:
                    continue
                total_rows_updated += 1
                if dry_run:
                    logger.info('[dry-run] Would update %s.%s pk=%s cols=%s', table_name, alias, pk_val, list(updates.keys()))
                    continue
                set_parts = ', '.join(f'`{c}` = %s' for c in updates)
                update_sql = f"UPDATE `{safe_table}` SET {set_parts} WHERE `{pk_col.replace('`', '``')}` = %s"
                params = [updates[c] for c in updates] + [pk_val]
                cur.execute(update_sql, params)
    return tables_processed, total_rows_updated


class Command(BaseCommand):
    help = (
        'Remove JSON from text columns in cheradip_honours and cheradip_hsc; '
        'replace with plain text extracted from blocks[].text.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only report what would be updated; do not write.',
        )
        parser.add_argument(
            '--db',
            type=str,
            choices=['honours', 'hsc'],
            default=None,
            help='Process only this database (default: both).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        db_choice = options['db']
        if dry_run:
            self.stdout.write('Dry run: no changes will be written.')
        for alias in ('honours', 'hsc'):
            if db_choice and alias != db_choice:
                continue
            self.stdout.write(f'Processing database: {alias} ...')
            tables_processed, rows_updated = process_database(alias, dry_run=dry_run)
            self.stdout.write(self.style.SUCCESS(
                f'  {alias}: {tables_processed} tables processed, {rows_updated} rows updated.'
            ))
        self.stdout.write(self.style.SUCCESS('Done.'))
