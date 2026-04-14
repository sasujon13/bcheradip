r"""
Load question rows from CSV files into HSC subject question tables (cheradip_hsc).


CSV files are named as the table name (e.g. cheradip_higher_secon_11_12_information_and_communication_techno.csv)
and live under a directory (default: C:\Users\sasha\Desktop\database\insert_daricomma).
All .csv files in the directory are processed; each file is inserted into the HSC table with the same name as the file (without .csv).

CSV may contain Bengali text and special characters; files are read as UTF-8 (with BOM handled).

Common CSV headers; handling:
- id column: ignored (not inserted). CSV may have an "id" or "ID" column; it is always skipped.
- First **data** row after the header is skipped when it repeats column titles (common export quirk);
  only the header row is used for DictReader field names.
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
import hashlib
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
DEFAULT_CSV_DIR = Path(r'D:\VSCode\database\insert_daricomma')
DEFAULT_UPDATED_BY = 'Cheradip'


def _raise_csv_field_limit() -> None:
    """Python csv default max field size is 128KiB; question cells with [IMG] / long text can exceed it."""
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(2**31 - 1)


_raise_csv_field_limit()

# qid format is "{chapter_token}_{topic_no}_{seq}"; MySQL column was VARCHAR(64). Long or
# misplaced chapter_no in CSV would overflow — use a short deterministic token when needed.
_MAX_CHAPTER_TOKEN_FOR_QID = 24


def _chapter_token_for_qid(chapter_no: str) -> str:
    """
    Stable short string for next_qid_for_chapter_topic prefix segment.
    Keeps normal chapter labels (e.g. '01', short Bengali digits); hashes very long values
    (misaligned CSV / prose in ChapterNo) so qid fits VARCHAR(64).
    """
    s = (chapter_no or "").strip() or "0"
    if len(s) <= _MAX_CHAPTER_TOKEN_FOR_QID:
        return s
    return "c" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


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
    Widen string columns so long CSV/HTML (e.g. [IMG] lines) fits.

    - answer, option_1..4: VARCHAR → TEXT (same as before).
    - question, explanation, explanation2, explanation3: VARCHAR/TEXT → LONGTEXT
      (avoids \"Data too long for column 'explanation'\" when content > 64KB TEXT cap).
    Safe to run multiple times; skips columns already LONGTEXT or missing.
    """
    safe_name = table_name.replace('`', '``')

    def _modify_if_needed(col: str, use_longtext: bool) -> None:
        cursor.execute(
            """SELECT DATA_TYPE FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s AND column_name = %s""",
            [db_name, table_name, col],
        )
        row = cursor.fetchone()
        if not row:
            return
        dt = (row[0] or '').lower()
        if dt == 'longtext':
            return
        if use_longtext:
            if dt in ('varchar', 'char', 'text', 'tinytext', 'mediumtext'):
                cursor.execute(
                    f"ALTER TABLE `{safe_name}` MODIFY COLUMN `{col}` LONGTEXT NULL"
                )
        else:
            cursor.execute(
                """SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns
                   WHERE table_schema = %s AND table_name = %s AND column_name = %s""",
                [db_name, table_name, col],
            )
            row2 = cursor.fetchone()
            if (
                row2
                and row2[0] == 'varchar'
                and row2[1]
                and row2[1] < 65535
            ):
                cursor.execute(
                    f"ALTER TABLE `{safe_name}` MODIFY COLUMN `{col}` TEXT NULL"
                )

    for col in ('answer', 'option_1', 'option_2', 'option_3', 'option_4'):
        _modify_if_needed(col, use_longtext=False)
    for col in ('question', 'explanation', 'explanation2', 'explanation3'):
        _modify_if_needed(col, use_longtext=True)


def extend_qid_column_if_narrow(cursor, table_name, db_name, min_len: int = 191):
    """
    Widen qid from VARCHAR(64) when needed so long tokens / legacy rows do not fail inserts.

    Safe to run multiple times.
    """
    safe_name = table_name.replace("`", "``")
    cursor.execute(
        """SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns
           WHERE table_schema = %s AND table_name = %s AND column_name = 'qid'""",
        [db_name, table_name],
    )
    row = cursor.fetchone()
    if not row or row[0] is None:
        return
    cur_len = int(row[0])
    if cur_len >= min_len:
        return
    cursor.execute(
        f"ALTER TABLE `{safe_name}` MODIFY COLUMN `qid` VARCHAR({min_len}) NOT NULL"
    )


def extend_chapter_no_to_text(cursor, table_name, db_name):
    """
    Widen chapter_no (default VARCHAR(50) in CREATE TABLE) to TEXT so misaligned or
    long CSV values do not fail with \"Data too long for column 'chapter_no'\".
    Safe to run multiple times.
    """
    safe_name = table_name.replace("`", "``")
    cursor.execute(
        """SELECT DATA_TYPE FROM information_schema.columns
           WHERE table_schema = %s AND table_name = %s AND column_name = 'chapter_no'""",
        [db_name, table_name],
    )
    row = cursor.fetchone()
    if not row:
        return
    dt = (row[0] or "").lower()
    if dt in ("text", "mediumtext", "longtext", "tinytext"):
        return
    if dt in ("varchar", "char"):
        cursor.execute(
            f"ALTER TABLE `{safe_name}` MODIFY COLUMN `chapter_no` TEXT NULL"
        )


def extend_metadata_varchar_to_text(cursor, table_name, db_name):
    """
    Widen remaining short VARCHAR columns (subject, chapter, topic, topic_no, type,
    level, subsource) to TEXT so misaligned long CSV values do not hit VARCHAR limits.

    chapter_no is handled by extend_chapter_no_to_text. Safe to run multiple times.
    """
    safe_name = table_name.replace("`", "``")
    for col in (
        "subject",
        "chapter",
        "topic",
        "topic_no",
        "type",
        "level",
        "subsource",
    ):
        cursor.execute(
            """SELECT DATA_TYPE FROM information_schema.columns
               WHERE table_schema = %s AND table_name = %s AND column_name = %s""",
            [db_name, table_name, col],
        )
        row = cursor.fetchone()
        if not row:
            continue
        dt = (row[0] or "").lower()
        if dt in ("text", "mediumtext", "longtext", "tinytext"):
            continue
        if dt in ("varchar", "char"):
            cursor.execute(
                f"ALTER TABLE `{safe_name}` MODIFY COLUMN `{col}` TEXT NULL"
            )


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


def load_csv_rows(csv_path, skip_headers=None, *, skip_first_data_row: bool = True):
    """
    Read CSV and yield dicts keyed by header (lowercase).
    Supports Bengali text and special characters (UTF-8). BOM is handled (utf-8-sig).
    Columns in skip_headers are ignored (e.g. 'id' — CSV id column is never inserted).

    If skip_first_data_row is True (default), the first **data** row is not yielded — use when
    line 2 of the file repeats column headings instead of being a real question row.
    """
    skip_headers = set((s or '').strip().lower() for s in (skip_headers or []))
    # utf-8-sig: strip BOM if present; errors='replace': keep going on invalid bytes
    with open(csv_path, 'r', encoding='utf-8-sig', newline='', errors='replace') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
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
            if skip_first_data_row and i == 0:
                continue
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
        ch_tok = _chapter_token_for_qid(ch_no or '0')
        qid = next_qid_for_chapter_topic(table_name, ch_tok, topic_no, using=using)

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


def _stage_out(cmd, msg: str) -> None:
    """Print a trace line and flush so Windows consoles show output immediately."""
    cmd.stdout.write(f'[ensure_insertion] {msg}')
    try:
        cmd.stdout.flush()
    except Exception:
        pass


class Command(BaseCommand):
    help = (
        'Load questions from CSV files (named as table name) into cheradip_hsc. '
        'Skips ID; by default skips the first data row if it repeats headers; '
        'chapter_no → English; adds created_at, updated_at, updated_by, topic_no, qid; '
        'skips duplicate (question, answer).'
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
        parser.add_argument(
            '--keep-first-data-row',
            action='store_true',
            help=(
                'Include the first CSV data row (default: skip it when it repeats column headings).'
            ),
        )

    def handle(self, *args, **options):
        _stage_out(self, 'Stage 1: handle() started (command reached Django).')
        csv_dir = Path(options['dir']).resolve()
        single_table = options.get('table')
        dry_run = options['dry_run']
        keep_first = options.get('keep_first_data_row', False)
        _stage_out(
            self,
            f'Stage 2: options — dir={csv_dir!s}, table={single_table!r}, dry_run={dry_run}, '
            f'keep_first_data_row={keep_first}',
        )

        if not csv_dir.is_dir():
            self.stdout.write(self.style.ERROR(f'Directory not found: {csv_dir}'))
            self.stdout.write(self.style.WARNING('Cause: --dir path does not exist or is not a directory.'))
            _stage_out(self, 'STOP: bad --dir (exit).')
            return

        _stage_out(self, 'Stage 3: --dir exists and is a directory.')

        if single_table:
            csv_files = [csv_dir / f'{single_table}.csv']
            if not csv_files[0].exists():
                self.stdout.write(self.style.ERROR(f'File not found: {csv_files[0]}'))
                self.stdout.write(self.style.WARNING('Cause: no file named <table>.csv under --dir.'))
                _stage_out(self, 'STOP: --table file missing (exit).')
                return
        else:
            csv_files = sorted(csv_dir.glob('*.csv'))

        _stage_out(self, f'Stage 4: found {len(csv_files)} CSV file(s) (top-level *.csv only).')

        if not csv_files:
            self.stdout.write(self.style.WARNING(f'No CSV files in {csv_dir}'))
            self.stdout.write(
                self.style.WARNING(
                    'Cause: no *.csv in that folder (only top-level files count; subfolders are not scanned).'
                )
            )
            _stage_out(self, 'STOP: no csv files (exit).')
            return

        if HSC_ALIAS not in connections:
            self.stdout.write(self.style.ERROR('Database "hsc" is not configured.'))
            self.stdout.write(
                self.style.WARNING('Cause: DATABASES in settings has no alias "hsc" (wrong DJANGO_SETTINGS_MODULE?).')
            )
            _stage_out(self, 'STOP: hsc DB not configured (exit).')
            return

        _stage_out(self, f'Stage 5: database alias "{HSC_ALIAS}" is configured.')

        if dry_run:
            self.stdout.write(self.style.WARNING('Cause: --dry-run — listing rows only; nothing will be inserted.'))

        # Suppress SQL debug logging so Bengali/special chars in params don't cause UnicodeEncodeError on Windows
        db_logger = logging.getLogger(_DB_LOGGER)
        old_level = db_logger.level
        db_logger.setLevel(logging.WARNING)
        try:
            _stage_out(self, 'Stage 6: calling _run_inserts() ...')
            self._run_inserts(
                csv_files,
                dry_run,
                keep_first_data_row=keep_first,
            )
            _stage_out(self, 'Stage 7: _run_inserts() returned normally.')
        finally:
            db_logger.setLevel(old_level)

    def _run_inserts(self, csv_files, dry_run, *, keep_first_data_row: bool = False):
        """Process each CSV and insert into the table named by the file (stem)."""
        _stage_out(self, f'Stage 6a: _run_inserts loop, {len(csv_files)} file(s).')
        for csv_path in csv_files:
            table_name = csv_path.stem
            _stage_out(self, f'Stage 6b: file={csv_path.name!r} -> table={table_name!r}')
            try:
                rows = list(
                    load_csv_rows(
                        csv_path,
                        skip_headers=['id'],
                        skip_first_data_row=not keep_first_data_row,
                    )
                )
                _stage_out(self, f'Stage 6c: read {len(rows)} row(s) from CSV.')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'{csv_path.name}: read failed: {e}'))
                self.stdout.write(
                    self.style.WARNING(
                        '  Cause: invalid CSV/encoding/path, or (before fix) a field >128KiB per cell.'
                    )
                )
                continue

            if dry_run:
                self.stdout.write(f'{table_name}: {len(rows)} row(s) (dry run, no insert).')
                continue

            if not rows:
                self.stdout.write(f'{table_name}: 0 rows, skip.')
                self.stdout.write(
                    self.style.WARNING(
                        '  Cause: file is empty or has no data rows after the header '
                        '(or only a skipped duplicate header row; use --keep-first-data-row if needed).'
                    )
                )
                continue

            if not ensure_table_exists(table_name, using=HSC_ALIAS):
                self.stdout.write(self.style.WARNING(f'Table {table_name} does not exist. Run ensure_hsc first. Skip.'))
                self.stdout.write(
                    self.style.WARNING(
                        f'  Cause: CSV filename (without .csv) must match an HSC subject table name; '
                        f'table "{table_name}" is missing in DB "{connections[HSC_ALIAS].settings_dict.get("NAME", "")}".'
                    )
                )
                _stage_out(self, f'Stage 6d: SKIP table missing for {table_name!r}.')
                continue

            _stage_out(self, f'Stage 6d: table {table_name!r} exists; altering columns if needed, then inserting ...')
            conn = connections[HSC_ALIAS]
            db_name = conn.settings_dict.get('NAME', '')
            with conn.cursor() as cur:
                drop_id_column_if_present(cur, table_name, db_name)
                extend_answer_and_options_to_text(cur, table_name, db_name)
                extend_chapter_no_to_text(cur, table_name, db_name)
                extend_metadata_varchar_to_text(cur, table_name, db_name)
                extend_qid_column_if_narrow(cur, table_name, db_name)
                try:
                    # Show a single updating progress line per table in the console.
                    inserted, skipped = insert_csv_rows(
                        cur,
                        table_name,
                        rows,
                        using=HSC_ALIAS,
                        progress_prefix=table_name,
                    )
                    self.stdout.write(
                        f'{table_name}: finished — inserted={inserted}, skipped_duplicate={skipped} '
                        f'(duplicates: same question+answer already in table).'
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'{table_name}: {e}'))
                    self.stdout.write(
                        self.style.WARNING(
                            '  Cause: insert failed (missing columns chapter_no/topic/question/answer, '
                            'SQL error, or constraint). See message above.'
                        )
                    )
        _stage_out(self, 'Stage 6z: finished all CSV files in this run.')


if __name__ == '__main__':
    print(
        'Do not run this file directly. Use Django:\n'
        '  cd <project_with_manage.py>\n'
        '  python manage.py ensure_insertion [--dir PATH] [--dry-run]\n',
        file=sys.stderr,
    )
    sys.exit(2)
