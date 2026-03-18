"""
Ensure the HSC database (cheradip_hsc) has:
- cheradip_pending_question_request, cheradip_pending_subject_request, cheradip_subject
- One subject question table per (class_level, subject_tr) from cheradip_subject (via subject_question_tables)

On every run: check if tables exist; first alter cheradip_pending_subject_request_hsc to
cheradip_pending_subject_request when the old table exists and the new one does not; then
create only missing tables (existing tables are left unchanged).

Usage:
  python manage.py ensure_hsc
  python manage.py ensure_hsc --check-only   # only verify, do not create tables
"""
from django.core.management.base import BaseCommand
from django.db import connections

HSC_ALIAS = 'hsc'

# HSC: cheradip_subject (same structure as honours)
CREATE_CHERADIP_SUBJECT = """
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# HSC: cheradip_pending_subject_request (unified name; was cheradip_pending_subject_request_hsc)
CREATE_PENDING_SUBJECT_REQUEST = """
CREATE TABLE IF NOT EXISTS cheradip_pending_subject_request (
    id BIGINT AUTO_INCREMENT NOT NULL PRIMARY KEY,
    subject_name VARCHAR(255) NOT NULL,
    subject_tr VARCHAR(255) NOT NULL,
    level_tr VARCHAR(100) NULL,
    class_level VARCHAR(50) NULL,
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

# HSC: cheradip_pending_question_request (pending questions for HSC; approved get qid in subject question tables)
CREATE_PENDING_QUESTION_REQUEST = """
CREATE TABLE IF NOT EXISTS cheradip_pending_question_request (
    id INT AUTO_INCREMENT NOT NULL PRIMARY KEY,
    level_tr VARCHAR(100) NULL,
    class_level VARCHAR(50) NULL,
    subject_tr VARCHAR(255) NOT NULL,
    chapter_no VARCHAR(50) NULL,
    chapter VARCHAR(255) NOT NULL,
    topic_no VARCHAR(50) NULL,
    topic VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    option_1 TEXT NULL,
    option_2 TEXT NULL,
    option_3 TEXT NULL,
    option_4 TEXT NULL,
    answer TEXT NULL,
    explanation TEXT NULL,
    explanation2 TEXT NULL,
    explanation3 TEXT NULL,
    type VARCHAR(100) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at DATETIME(6) NULL,
    approved_at DATETIME(6) NULL,
    approved_qid VARCHAR(64) NULL,
    requested_qid VARCHAR(64) NULL COMMENT 'qid of question being edited',
    INDEX (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def _ensure_hsc_base_tables(cursor, db_name, dry_run):
    """On every run: first rename cheradip_pending_subject_request_hsc to cheradip_pending_subject_request if old exists and new does not; then create any missing tables (existing ones are left unchanged)."""
    if dry_run:
        return
    # First: alter/rename old table to cheradip_pending_subject_request when applicable
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
        [db_name, 'cheradip_pending_subject_request_hsc']
    )
    has_old = cursor.fetchone()
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
        [db_name, 'cheradip_pending_subject_request']
    )
    has_new = cursor.fetchone()
    if has_old and not has_new:
        cursor.execute("RENAME TABLE cheradip_pending_subject_request_hsc TO cheradip_pending_subject_request")
    # Then: create only missing tables (IF NOT EXISTS; existing tables ignored)
    cursor.execute(CREATE_CHERADIP_SUBJECT)
    cursor.execute(CREATE_PENDING_SUBJECT_REQUEST)
    cursor.execute(CREATE_PENDING_QUESTION_REQUEST)
    # Add requested_qid to existing cheradip_pending_question_request if missing
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = 'cheradip_pending_question_request' AND column_name = 'requested_qid'",
        [db_name]
    )
    if not cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE cheradip_pending_question_request ADD COLUMN requested_qid VARCHAR(64) NULL COMMENT 'qid of question being edited'")
        except Exception:
            pass


class Command(BaseCommand):
    help = (
        'Ensure cheradip_hsc has cheradip_pending_question_request, '
        'cheradip_pending_subject_request, cheradip_subject, and dynamic subject question tables (qid PK, topic_no).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only verify tables exist; do not create tables.',
        )

    def handle(self, *args, **options):
        if HSC_ALIAS not in connections:
            self.stdout.write(self.style.ERROR('Database "hsc" is not configured.'))
            return

        db_name = connections[HSC_ALIAS].settings_dict.get('NAME', '')
        self.stdout.write('Database: %s (hsc)' % db_name)

        if not options['check_only']:
            with connections[HSC_ALIAS].cursor() as cur:
                _ensure_hsc_base_tables(cur, db_name, False)
            self.stdout.write('Ensured cheradip_pending_question_request, cheradip_pending_subject_request, cheradip_subject.')

            from cheradip.subject_question_tables import ensure_subject_question_tables
            created, total = ensure_subject_question_tables(verbose=True, using=HSC_ALIAS)
            if created > 0:
                self.stdout.write(self.style.SUCCESS('Created %d subject question table(s) (qid PK, topic_no).' % created))
            self.stdout.write('Subject question tables: %d expected (from cheradip_subject).' % total)

        with connections[HSC_ALIAS].cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE'",
                [db_name],
            )
            existing = {row[0] for row in cur.fetchall()}

        for name in ('cheradip_pending_question_request', 'cheradip_pending_subject_request', 'cheradip_subject'):
            if name in existing:
                self.stdout.write(self.style.SUCCESS('%s present.' % name))
            else:
                self.stdout.write(self.style.WARNING('%s missing. Run ensure_hsc without --check-only.' % name))

        self.stdout.write(self.style.SUCCESS('Ensure HSC complete.'))
