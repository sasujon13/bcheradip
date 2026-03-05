"""
Shared logic for subject question tables: create tables from cheradip_subject.
Used by migration 0010, post_migrate signal, and management commands.
One table per (class_level, subject_translated); first row (by id) gives level_tr for the name.
"""
import re
from django.db import connection

MYSQL_MAX_TABLE_NAME_LEN = 64

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
)
"""


def _slug(s):
    if not s or not isinstance(s, str):
        return 'unknown'
    s = s.strip().lower().replace(' ', '_').replace('-', '_')
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'unknown'


def subject_question_table_name(level_tr, class_level, subject_translated):
    a = _slug(level_tr)[:12]
    b = _slug(class_level)[:8]
    c = _slug(subject_translated)[:36]
    name = f'cheradip_{a}_{b}_{c}'.rstrip('_')
    if len(name) > MYSQL_MAX_TABLE_NAME_LEN:
        name = name[:MYSQL_MAX_TABLE_NAME_LEN].rstrip('_')
    return name


def ensure_subject_question_tables(verbose=False):
    """
    Create any missing subject question tables from current cheradip_subject.
    One table per (class_level, subject_translated), first row by id.
    Uses CREATE TABLE IF NOT EXISTS so existing tables and data are left unchanged.
    Returns (created_count, total_expected).
    """
    from cheradip.models import Subject

    seen_key = set()
    created = 0
    with connection.cursor() as cur:
        for row in Subject.objects.order_by('id').values_list('level_tr', 'class_level', 'subject_translated'):
            level_tr = row[0] or ''
            class_level = row[1] or ''
            subject_translated = row[2] or ''
            key = (class_level, subject_translated)
            if key in seen_key:
                continue
            seen_key.add(key)
            name = subject_question_table_name(level_tr, class_level, subject_translated)
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s", [name])
            if cur.fetchone():
                continue
            cur.execute(CREATE_TABLE_SQL.format(table_name=name))
            created += 1
            if verbose:
                print(f'Created {name}')
    return created, len(seen_key)
