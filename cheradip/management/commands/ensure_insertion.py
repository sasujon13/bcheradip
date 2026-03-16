r"""
Load question rows from CSV files into HSC subject question tables (cheradip_hsc).


CSV files are named as the table name (e.g. cheradip_higher_secon_11_12_information_and_communication_techno.csv)
and live under a directory (default: C:\Users\sasha\Desktop\database\insert_daricomma).
All .csv files in the directory are processed; each file is inserted into the HSC table with the same name as the file (without .csv).

CSV may contain Bengali text and special characters; files are read as UTF-8 (with BOM handled).

Common CSV headers; handling:
- id column: ignored (not inserted). CSV may have an "id" or "ID" column; it is always skipped.
- chapter_no: converted to English (Bengali digits ০–১২ → 0–12).
- Auto-added on insert: created_at, updated_at (current datetime), updated_by (default "Cheradip"),
  topic_no (1, 2, 3... per chapter+topic), qid (next from table).
- Duplicate: if (question, answer) already exists in the table, row is skipped.

Usage:
  python manage.py ensure_insertion
  python manage.py ensure_insertion --dir "C:\Users\sasha\Desktop\database\insert_daricomma"
  python manage.py ensure_insertion --table cheradip_higher_secon_11_12_information_and_communication_techno
  python manage.py ensure_insertion --dry-run
"""
import csv
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connections

# Avoid UnicodeEncodeError when logging SQL that contains Bengali/special chars (Windows cp1252)
_DB_LOGGER = 'django.db.backends'

HSC_ALIAS = 'hsc'
DEFAULT_CSV_DIR = Path(r'C:\Users\sasha\Desktop\database\insert_daricomma')
DEFAULT_UPDATED_BY = 'Cheradip'

# Bengali digit / number → English (replace longer first)
BENGALI_TO_ENGLISH = [
    ('১২', '12'), ('১১', '11'), ('১০', '10'),
    ('৯', '9'), ('৮', '8'), ('৭', '7'), ('৬', '6'),
    ('৫', '5'), ('৪', '4'), ('৩', '3'), ('২', '2'), ('১', '1'), ('০', '0'),
]


def bengali_to_english(s):
    """Replace Bengali digits/numbers with English in string s."""
    if not s:
        return s
    out = s
    for bn, en in BENGALI_TO_ENGLISH:
        out = out.replace(bn, en)
    return out


def ensure_table_exists(table_name, using='hsc'):
    """Ensure the subject question table exists in the given DB (e.g. ensure_hsc)."""
    if using not in connections:
        return False
    from cheradip.subject_question_tables import ensure_subject_question_tables
    ensure_subject_question_tables(verbose=False, using=using)
    conn = connections[using]
    db_name = conn.settings_dict.get('NAME', '')
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
            [db_name, table_name]
        )
        return cur.fetchone() is not None


def extend_answer_and_options_to_text(cursor, table_name, db_name):
    """
    Alter answer and option_1..4 to TEXT if they are VARCHAR (e.g. 500), so long content fits.
    Safe to run multiple times; only modifies columns that are still VARCHAR.
    """
    safe_name = table_name.replace('`', '``')
    for col in ('answer', 'option_1', 'option_2', 'option_3', 'option_4'):
        cursor.execute(
            """SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s AND column_name = %s""",
            [db_name, table_name, col]
        )
        row = cursor.fetchone()
        if row and row[0] == 'varchar' and row[1] and row[1] < 65535:
            cursor.execute(f"ALTER TABLE `{safe_name}` MODIFY COLUMN `{col}` TEXT NULL")


def drop_id_column_if_present(cursor, table_name, db_name):
    """
    Drop the id column if the table has it. Subject question tables use qid as primary key only.
    If id is the current primary key, drop it first then drop the column; ensure qid is the PK.
    """
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = 'id'",
        [db_name, table_name]
    )
    if not cursor.fetchone():
        return
    safe_name = table_name.replace('`', '``')
    cursor.execute(
        """SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
           WHERE table_schema = %s AND table_name = %s AND constraint_name = 'PRIMARY'""",
        [db_name, table_name]
    )
    pk_cols = [row[0] for row in cursor.fetchall()]
    if pk_cols == ['id']:
        cursor.execute(f"ALTER TABLE `{safe_name}` DROP PRIMARY KEY")
    cursor.execute(f"ALTER TABLE `{safe_name}` DROP COLUMN `id`")
    if 'qid' not in pk_cols:
        cursor.execute(f"ALTER TABLE `{safe_name}` ADD PRIMARY KEY (`qid`)")

# Table columns in insert order (same as subject question tables)
TABLE_COLUMNS = [
    'qid', 'subject', 'chapter_no', 'chapter', 'topic_no', 'topic',
    'question', 'option_1', 'option_2', 'option_3', 'option_4',
    'answer', 'explanation', 'explanation2', 'explanation3',
    'type', 'level', 'subsource', 'created_at', 'updated_at', 'updated_by'
]

# CSV header aliases: alternate header names (lowercase) -> canonical column name
# e.g. ChapterNo -> chapter_no, Topic -> topic, Option 1 -> option_1, Question Type -> type
CSV_HEADER_ALIASES = {
    'chapterno': 'chapter_no',
    'chapter no': 'chapter_no',
    'topic': 'topic',
    'option 1': 'option_1',
    'option 2': 'option_2',
    'option 3': 'option_3',
    'option 4': 'option_4',
    'question type': 'type',
    'subsources': 'subsource',
}


def normalize_csv_value(v):
    if v is None or (isinstance(v, str) and v.strip() == ''):
        return None
    if isinstance(v, str):
        v = v.strip()
    return v


def normalize_level(s):
    """Remove leading 'MCQ: ', 'MCQ:', 'CQ: ', 'CQ:' from level (case-insensitive) before insertion."""
    if not s or not isinstance(s, str):
        return s
    s = s.strip()
    lower = s.lower()
    for prefix in ('mcq: ', 'mcq:', 'cq: ', 'cq:'):
        if lower.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    return s or None


def load_csv_rows(csv_path, skip_headers=None):
    """
    Read CSV and yield dicts keyed by header (lowercase).
    Supports Bengali text and special characters (UTF-8). BOM is handled (utf-8-sig).
    Columns in skip_headers are ignored (e.g. 'id' — CSV id column is never inserted).
    """
    skip_headers = set((s or '').strip().lower() for s in (skip_headers or []))
    # utf-8-sig: strip BOM if present; errors='replace': keep going on invalid bytes
    with open(csv_path, 'r', encoding='utf-8-sig', newline='', errors='replace') as f:
        reader = csv.DictReader(f)
        fieldnames = [fn for fn in (reader.fieldnames or []) if fn.strip().lower() not in skip_headers]
        for row in reader:
            out = {}
            for k, v in row.items():
                key = (k or '').strip()
                if key.lower() in skip_headers:
                    continue
                out[key.lower()] = normalize_csv_value(v)
            # Map alternate headers to canonical names (e.g. ChapterNo -> chapter_no, Topic -> topic)
            for alt, canonical in CSV_HEADER_ALIASES.items():
                if canonical not in out and alt in out:
                    out[canonical] = out[alt]
            yield out


def insert_csv_rows(cursor, table_name, rows, using=None, progress_prefix=None):
    """
    rows: list of dicts (keys lowercase, from CSV minus ID).
    Apply: chapter_no → English; add created_at, updated_at, updated_by, topic_no, qid.
    Skip duplicate (question, answer). Return (inserted, skipped).
    """
    from cheradip.subject_question_tables import next_qid_for_chapter_topic

    if not rows:
        return 0, 0

    # Require chapter_no and topic for topic_no / qid
    sample = rows[0]
    if 'chapter_no' not in sample or 'topic' not in sample:
        raise ValueError('CSV must have chapter_no and topic columns.')
    if 'question' not in sample or 'answer' not in sample:
        raise ValueError('CSV must have question and answer columns.')

    # Assign topic_no per (chapter_no, topic): 1, 2, 3... by first appearance order in CSV
    # First row's topic in a chapter gets 1, next unique topic gets 2, etc.
    key_to_topic_no = {}
    next_seq_per_chapter = defaultdict(int)
    for row in rows:
        ch_no = bengali_to_english((row.get('chapter_no') or '').strip())
        topic = (row.get('topic') or '').strip()
        key = (ch_no, topic)
        if key not in key_to_topic_no:
            next_seq_per_chapter[ch_no] += 1
            key_to_topic_no[key] = str(next_seq_per_chapter[ch_no])

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    safe_name = table_name.replace('`', '``')
    inserted = 0
    skipped_duplicate = 0
    # Update progress line every N rows and use \r to overwrite same line (only when stdout is a TTY)
    progress_interval = 100
    use_live_progress = progress_prefix and getattr(sys.stdout, 'isatty', lambda: False)()

    def _write_progress(force=False):
        if not progress_prefix:
            return
        total = inserted + skipped_duplicate
        if not force and not use_live_progress:
            return
        msg = f"{progress_prefix}: {inserted} Inserted {skipped_duplicate} Skipped (Duplicate)"
        if use_live_progress:
            # Pad to 120 chars so \r overwrites any longer previous line
            sys.stdout.write("\r" + msg + " " * max(0, 120 - len(msg)))
            sys.stdout.flush()
        elif force:
            sys.stdout.write(msg + "\n")
            sys.stdout.flush()

    for row in rows:
        ch_no = bengali_to_english((row.get('chapter_no') or '').strip())
        topic = (row.get('topic') or '').strip()
        topic_no = key_to_topic_no.get((ch_no, topic), '1')
        qid = next_qid_for_chapter_topic(table_name, ch_no or '0', topic_no, using=using)

        value_by_col = dict(row)
        value_by_col['chapter_no'] = ch_no or value_by_col.get('chapter_no')
        value_by_col['topic_no'] = topic_no
        value_by_col['qid'] = qid
        value_by_col['created_at'] = now
        value_by_col['updated_at'] = now
        value_by_col['updated_by'] = value_by_col.get('updated_by') or DEFAULT_UPDATED_BY
        value_by_col['level'] = normalize_level(value_by_col.get('level') or '')

        question_val = value_by_col.get('question')
        answer_val = value_by_col.get('answer')
        cursor.execute(
            f"SELECT 1 FROM `{safe_name}` WHERE question = %s AND answer = %s LIMIT 1",
            [question_val, answer_val]
        )
        if cursor.fetchone():
            skipped_duplicate += 1
            total = inserted + skipped_duplicate
            if progress_prefix and (total % progress_interval == 0 or total == 1):
                _write_progress()
            continue

        vals = []
        for c in TABLE_COLUMNS:
            v = value_by_col.get(c.lower())
            if v is None:
                vals.append(None)
            else:
                vals.append(v)
        placeholders = ', '.join(['%s'] * len(TABLE_COLUMNS))
        cols_str = ', '.join(f'`{c}`' for c in TABLE_COLUMNS)
        try:
            cursor.execute(
                f"INSERT INTO `{table_name}` ({cols_str}) VALUES ({placeholders})",
                vals
            )
            inserted += 1
        except Exception as e:
            raise RuntimeError(f"Insert failed for qid={qid}: {e}") from e

        total = inserted + skipped_duplicate
        if progress_prefix and (total % progress_interval == 0 or total == 1):
            _write_progress()

    if progress_prefix:
        _write_progress(force=True)
        if use_live_progress:
            # So the next table or shell prompt starts on a new line
            sys.stdout.write("\n")
            sys.stdout.flush()

    return inserted, skipped_duplicate


class Command(BaseCommand):
    help = (
        'Load questions from CSV files (named as table name) into cheradip_hsc. '
        'Skips ID; chapter_no → English; adds created_at, updated_at, updated_by, topic_no, qid; skips duplicate (question, answer).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir',
            type=str,
            default=str(DEFAULT_CSV_DIR),
            help=f'Directory containing CSV files (default: {DEFAULT_CSV_DIR}).',
        )
        parser.add_argument(
            '--table',
            type=str,
            default=None,
            help='Load only this table (file: <table>.csv). If not set, load all CSV files in --dir.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List CSV files and row counts only; do not insert.',
        )

    def handle(self, *args, **options):
        csv_dir = Path(options['dir']).resolve()
        single_table = options.get('table')
        dry_run = options['dry_run']

        if not csv_dir.is_dir():
            self.stdout.write(self.style.ERROR(f'Directory not found: {csv_dir}'))
            return

        if single_table:
            csv_files = [csv_dir / f'{single_table}.csv']
            if not csv_files[0].exists():
                self.stdout.write(self.style.ERROR(f'File not found: {csv_files[0]}'))
                return
        else:
            csv_files = sorted(csv_dir.glob('*.csv'))

        if not csv_files:
            self.stdout.write(self.style.WARNING(f'No CSV files in {csv_dir}'))
            return

        if HSC_ALIAS not in connections:
            self.stdout.write(self.style.ERROR('Database "hsc" is not configured.'))
            return

        # Suppress SQL debug logging so Bengali/special chars in params don't cause UnicodeEncodeError on Windows
        db_logger = logging.getLogger(_DB_LOGGER)
        old_level = db_logger.level
        db_logger.setLevel(logging.WARNING)
        try:
            self._run_inserts(csv_files, dry_run)
        finally:
            db_logger.setLevel(old_level)

    def _run_inserts(self, csv_files, dry_run):
        """Process each CSV and insert into the table named by the file (stem)."""
        for csv_path in csv_files:
            table_name = csv_path.stem
            try:
                rows = list(load_csv_rows(csv_path, skip_headers=['id']))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'{csv_path.name}: read failed: {e}'))
                continue

            if dry_run:
                self.stdout.write(f'{table_name}: {len(rows)} row(s) (dry run, no insert).')
                continue

            if not rows:
                self.stdout.write(f'{table_name}: 0 rows, skip.')
                continue

            if not ensure_table_exists(table_name, using=HSC_ALIAS):
                self.stdout.write(self.style.WARNING(f'Table {table_name} does not exist. Run ensure_hsc first. Skip.'))
                continue

            conn = connections[HSC_ALIAS]
            db_name = conn.settings_dict.get('NAME', '')
            with conn.cursor() as cur:
                drop_id_column_if_present(cur, table_name, db_name)
                extend_answer_and_options_to_text(cur, table_name, db_name)
                try:
                    # Show a single updating progress line per table in the console.
                    inserted, skipped = insert_csv_rows(
                        cur,
                        table_name,
                        rows,
                        using=HSC_ALIAS,
                        progress_prefix=table_name,
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'{table_name}: {e}'))
