"""
Retrieve all unique book_tr from cheradip_subject in cheradip_honours
and create one question table per book_tr (same structure as subject question tables in cheradip_hsc).

Ensures cheradip_subject and cheradip_pending_subject_request_honours exist in cheradip_honours first (creates if missing).

Table names: cheradip_honours_{slug(book_tr)} (e.g. cheradip_honours_ict).
Structure: id, subject, chapter_no, chapter, topic, question, option_1..4, answer, explanation, etc.

Run:
  python manage.py ensure_honours
  python manage.py ensure_honours --dry-run
"""
import re
from django.core.management.base import BaseCommand
from django.db import connections

MYSQL_MAX_TABLE_NAME_LEN = 64

# Honours: cheradip_subject (with book_tr, book_name for honours)
CREATE_CHERADIP_SUBJECT_HONOURS = """
CREATE TABLE IF NOT EXISTS cheradip_subject (
    id INT AUTO_INCREMENT PRIMARY KEY,
    level VARCHAR(100) NULL,
    level_tr VARCHAR(100) NULL,
    groups JSON NULL,
    class_level VARCHAR(10) NULL,
    subject_name VARCHAR(255) NULL,
    subject_tr VARCHAR(255) NULL,
    subject_code VARCHAR(12) NOT NULL,
    country_id VARCHAR(2) NULL,
    language_code VARCHAR(10) NULL,
    book_name VARCHAR(255) NULL,
    book_tr VARCHAR(255) NULL,
    created_at DATETIME(6) NULL,
    updated_at DATETIME(6) NULL,
    UNIQUE KEY (subject_code),
    INDEX (subject_code),
    INDEX (country_id),
    INDEX (country_id, level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 AUTO_INCREMENT=1;
"""

# Honours: cheradip_pending_subject_request_honours (degree_type; no level_tr/class_level)
CREATE_PENDING_SUBJECT_REQUEST_HONOURS = """
CREATE TABLE IF NOT EXISTS cheradip_pending_subject_request_honours (
    id BIGINT AUTO_INCREMENT NOT NULL PRIMARY KEY,
    subject_name VARCHAR(255) NOT NULL,
    subject_tr VARCHAR(255) NOT NULL,
    degree_type VARCHAR(50) NULL,
    country_id VARCHAR(2) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    reviewed_at DATETIME(6) NULL,
    reviewed_by_id INT NULL,
    notes LONGTEXT NULL,
    INDEX (country_id),
    INDEX (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# Same structure as subject question tables (cheradip_hsc / default)
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `{table_name}` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subject VARCHAR(255) NULL,
    chapter_no VARCHAR(50) NULL,
    chapter VARCHAR(255) NULL,
    topic VARCHAR(255) NULL,
    question TEXT NULL,
    option_1 VARCHAR(500) NULL,
    option_2 VARCHAR(500) NULL,
    option_3 VARCHAR(500) NULL,
    option_4 VARCHAR(500) NULL,
    answer VARCHAR(500) NULL,
    explanation TEXT NULL,
    explanation2 TEXT NULL,
    explanation3 TEXT NULL,
    type VARCHAR(100) NULL,
    level VARCHAR(100) NULL,
    subsource VARCHAR(255) NULL,
    created_at DATETIME(6) NULL,
    updated_at DATETIME(6) NULL,
    updated_by VARCHAR(255) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 AUTO_INCREMENT=1
"""


def _slug(s):
    if not s or not isinstance(s, str):
        return 'unknown'
    s = s.strip().lower().replace(' ', '_').replace('-', '_')
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'unknown'


def book_question_table_name(book_tr):
    """e.g. ICT -> cheradip_honours_ict"""
    slug = _slug(book_tr)[:48]
    name = f'cheradip_honours_{slug}'.rstrip('_')
    if len(name) > MYSQL_MAX_TABLE_NAME_LEN:
        name = name[:MYSQL_MAX_TABLE_NAME_LEN].rstrip('_')
    return name or 'cheradip_honours_unknown'


def ensure_honours_sync():
    """
    Ensure base tables and create any missing book question tables in cheradip_honours.
    Call this after adding rows to honours.cheradip_subject (e.g. from admin approve or bulk import).
    Returns number of tables created, or -1 if honours DB unavailable.
    """
    if 'honours' not in connections:
        return -1
    conn = connections['honours']
    db_name = conn.settings_dict['NAME']
    with conn.cursor() as cur:
        cur.execute(CREATE_CHERADIP_SUBJECT_HONOURS)
        cur.execute(CREATE_PENDING_SUBJECT_REQUEST_HONOURS)
    # Ensure book_tr / book_name columns exist (e.g. table created by older migration)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema = %s AND table_name = 'cheradip_subject' AND COLUMN_NAME IN ('book_tr', 'book_name')",
            [db_name]
        )
        have = {row[0] for row in cur.fetchall()}
        for col, defn in (('book_name', 'VARCHAR(255) NULL'), ('book_tr', 'VARCHAR(255) NULL')):
            if col not in have:
                try:
                    with conn.cursor() as c2:
                        c2.execute("ALTER TABLE cheradip_subject ADD COLUMN %s %s" % (col, defn))
                except Exception:
                    pass
        cur.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = 'cheradip_subject' AND column_name = 'book_tr'",
            [db_name]
        )
        if not cur.fetchone():
            return -1
        cur.execute(
            "SELECT DISTINCT book_tr FROM cheradip_subject WHERE book_tr IS NOT NULL AND TRIM(COALESCE(book_tr, '')) != '' ORDER BY book_tr"
        )
        book_trs = [row[0] for row in cur.fetchall()]
    if not book_trs:
        return 0
    created = 0
    for book_tr in book_trs:
        table_name = book_question_table_name(book_tr)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                [db_name, table_name]
            )
            if cur.fetchone():
                continue
            cur.execute(CREATE_TABLE_SQL.format(table_name=table_name))
            created += 1
    return created


class Command(BaseCommand):
    help = 'Create question tables per unique book_tr in honours.cheradip_subject (same structure as hsc subject question tables)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        conn = connections['honours']
        db_name = conn.settings_dict['NAME']

        # Ensure base tables exist in cheradip_honours (create if missing)
        with conn.cursor() as cur:
            cur.execute(CREATE_CHERADIP_SUBJECT_HONOURS)
            cur.execute(CREATE_PENDING_SUBJECT_REQUEST_HONOURS)
        if not dry_run:
            self.stdout.write('Ensured cheradip_subject and cheradip_pending_subject_request_honours exist in honours.')

        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = 'cheradip_subject' AND column_name = 'book_tr'",
                [db_name]
            )
            if not cur.fetchone():
                self.stdout.write(self.style.ERROR('Column book_tr not found in %s.cheradip_subject.' % db_name))
                return

            cur.execute(
                "SELECT DISTINCT book_tr FROM cheradip_subject WHERE book_tr IS NOT NULL AND TRIM(COALESCE(book_tr, '')) != '' ORDER BY book_tr"
            )
            book_trs = [row[0] for row in cur.fetchall()]

        if not book_trs:
            self.stdout.write('No distinct book_tr found in honours.cheradip_subject.')
            return

        self.stdout.write('Unique book_tr: %s' % ', '.join(repr(b) for b in book_trs))

        created = 0
        for book_tr in book_trs:
            table_name = book_question_table_name(book_tr)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                    [db_name, table_name]
                )
                if cur.fetchone():
                    self.stdout.write('  %s (already exists)' % table_name)
                    continue
                if dry_run:
                    self.stdout.write('  Would create %s for book_tr=%r' % (table_name, book_tr))
                    created += 1
                    continue
                cur.execute(CREATE_TABLE_SQL.format(table_name=table_name))
                self.stdout.write('  Created %s for book_tr=%r' % (table_name, book_tr))
                created += 1

        if not dry_run and created > 0:
            self.stdout.write(self.style.SUCCESS('Created %d table(s).' % created))
        elif dry_run:
            self.stdout.write('Would create %d table(s).' % created)
