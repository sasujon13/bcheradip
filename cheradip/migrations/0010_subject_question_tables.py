# Create one question table per (class_level, subject_translated) from cheradip_subject (first row by id).
# Table names: cheradip_{level_tr}_{class_level}_{subject_translated} (lowercase, spaces/hyphens to underscore).
# On a new environment: after loading cheradip_subject data, run "python manage.py ensure_subject_question_tables"
# or run "migrate" again; post_migrate also ensures missing tables are created (see cheradip/apps.py).

import re
from django.db import migrations


MYSQL_MAX_TABLE_NAME_LEN = 64


def _slug(s):
    if not s or not isinstance(s, str):
        return 'unknown'
    s = s.strip().lower().replace(' ', '_').replace('-', '_')
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'unknown'


def table_name(level_tr, class_level, subject_translated):
    # Keep total length <= 64 by truncating parts: prefix=8, so 56 for level_class_subject (e.g. 12+8+36)
    a = _slug(level_tr)[:12]
    b = _slug(class_level)[:8]
    c = _slug(subject_translated)[:36]
    name = f'cheradip_{a}_{b}_{c}'.rstrip('_')
    if len(name) > MYSQL_MAX_TABLE_NAME_LEN:
        name = name[:MYSQL_MAX_TABLE_NAME_LEN].rstrip('_')
    return name


# SQL compatible with MySQL/MariaDB
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table_name} (
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
    question_level VARCHAR(100) NULL,
    subsource VARCHAR(255) NULL
)
"""


def create_question_tables(apps, schema_editor):
    # One table per (class_level, subject_translated); use first row (by id) for level_tr.
    Subject = apps.get_model('cheradip', 'Subject')
    seen_key = set()  # (class_level, subject_translated)
    with schema_editor.connection.cursor() as cur:
        for row in Subject.objects.order_by('id').values_list('level_tr', 'class_level', 'subject_translated'):
            level_tr = row[0] or ''
            class_level = row[1] or ''
            subject_translated = row[2] or ''
            key = (class_level, subject_translated)
            if key in seen_key:
                continue
            seen_key.add(key)
            name = table_name(level_tr, class_level, subject_translated)
            cur.execute(CREATE_TABLE_SQL.format(table_name=name))


def drop_question_tables(apps, schema_editor):
    Subject = apps.get_model('cheradip', 'Subject')
    seen_key = set()
    with schema_editor.connection.cursor() as cur:
        for row in Subject.objects.order_by('id').values_list('level_tr', 'class_level', 'subject_translated'):
            level_tr = row[0] or ''
            class_level = row[1] or ''
            subject_translated = row[2] or ''
            key = (class_level, subject_translated)
            if key in seen_key:
                continue
            seen_key.add(key)
            name = table_name(level_tr, class_level, subject_translated)
            cur.execute(f"DROP TABLE IF EXISTS `{name}`")


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0009_subject_subject_code_unique'),
    ]

    operations = [
        migrations.RunPython(create_question_tables, drop_question_tables),
    ]
