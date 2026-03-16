"""
Shared logic for subject question tables: create tables from cheradip_subject.
Used by migration 0010, post_migrate signal, and management commands.
One table per (class_level, subject_translated); first row (by id) gives level_tr for the name.
Supports multiple databases via using= (e.g. using='hsc' for cheradip_hsc).
"""
import re
from django.db import connection, connections

MYSQL_MAX_TABLE_NAME_LEN = 64

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `{table_name}` (
    qid VARCHAR(64) NOT NULL PRIMARY KEY,
    subject VARCHAR(255) NULL,
    chapter_no VARCHAR(50) NULL,
    chapter VARCHAR(255) NULL,
    topic_no VARCHAR(50) NULL,
    topic VARCHAR(255) NULL,
    question TEXT NULL,
    option_1 TEXT NULL,
    option_2 TEXT NULL,
    option_3 TEXT NULL,
    option_4 TEXT NULL,
    answer TEXT NULL,
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


def ensure_subject_question_tables(verbose=False, using=None):
    """
    Create any missing subject question tables from the cheradip_subject table in the given DB.
    One table per (class_level, subject_tr), first row by id.
    Uses CREATE TABLE IF NOT EXISTS so existing tables and data are left unchanged.
    Returns (created_count, total_expected).

    Reads from the cheradip_subject table via raw SQL (no Django Subject model).
    Columns used: level_tr, class_level, subject_tr (subject_tr used as subject_translated for table naming).
    If using is None, uses the default connection; if set (e.g. 'hsc'), uses that connection.
    """
    if using is None:
        conn = connection
        schema_sql = "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s"
        subject_sql = "SELECT level_tr, class_level, subject_tr FROM cheradip_subject ORDER BY id"
        schema_params_for = lambda name: [name]
    else:
        if using not in connections:
            return 0, 0
        conn = connections[using]
        db_name = conn.settings_dict.get('NAME', '')
        schema_sql = "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s"
        subject_sql = "SELECT level_tr, class_level, subject_tr FROM cheradip_subject ORDER BY id"
        schema_params_for = lambda name: [db_name, name]

    seen_key = set()
    created = 0
    with conn.cursor() as cur:
        try:
            cur.execute(subject_sql)
            rows = cur.fetchall()
        except Exception:
            rows = []
        for row in rows:
            level_tr = (row[0] or '').strip() if row[0] else ''
            class_level = (row[1] or '').strip() if row[1] else ''
            subject_translated = (row[2] or '').strip() if row[2] else ''
            key = (class_level, subject_translated)
            if key in seen_key:
                continue
            seen_key.add(key)
            name = subject_question_table_name(level_tr, class_level, subject_translated)
            cur.execute(schema_sql, schema_params_for(name))
            if cur.fetchone():
                continue
            cur.execute(CREATE_TABLE_SQL.format(table_name=name))
            created += 1
            if verbose:
                print(f'Created {name}')
    return created, len(seen_key)


def next_qid_for_chapter_topic(table_name, chapter_no, topic_no, using=None):
    """
    Generate next qid for (chapter_no, topic_no) in the given table.
    Format: chapter_no_topic_no_0001, 0002, 0003, ...
    chapter_no and topic_no are normalized (e.g. string, no spaces).
    Returns e.g. '1_1_0001' or '2_3_0042'.
    """
    conn = connections[using] if using and using in connections else connection
    prefix = f"{chapter_no or '0'}_{topic_no or '0'}_"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT qid FROM `{}` WHERE qid LIKE %s ORDER BY qid DESC LIMIT 1".format(table_name.replace('`', '``')),
            [prefix + '%']
        )
        row = cur.fetchone()
    if not row:
        return prefix + '0001'
    last = (row[0] or '').strip()
    if not last.startswith(prefix):
        return prefix + '0001'
    try:
        seq = int(last[len(prefix):])
        return prefix + f'{seq + 1:04d}'
    except (ValueError, TypeError):
        return prefix + '0001'


def drop_subject_question_table_if_unused(level_tr, class_level, subject_translated, using=None):
    """
    Drop the subject question table for (level_tr, class_level, subject_translated)
    if it exists and no row in cheradip_subject has the same (class_level, subject_tr).
    Reads from cheradip_subject via raw SQL (no Django Subject model).
    using: database alias (e.g. 'hsc'); if None, uses default connection.
    """
    conn = connections[using] if using and using in connections else connection
    db_name = conn.settings_dict.get('NAME', '')
    with conn.cursor() as cur:
        try:
            cur.execute(
                "SELECT 1 FROM cheradip_subject WHERE class_level = %s AND subject_tr = %s LIMIT 1",
                [class_level or '', subject_translated or '']
            )
            if cur.fetchone():
                return
        except Exception:
            pass
        name = subject_question_table_name(level_tr or '', class_level or '', subject_translated or '')
        if using:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s", [db_name, name])
        else:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s", [name])
        if cur.fetchone():
            cur.execute(f"DROP TABLE IF EXISTS `{name}`")
