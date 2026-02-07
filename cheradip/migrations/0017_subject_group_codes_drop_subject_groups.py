# Replace Subject M2M "groups" with JSONField "group_codes"; drop table cheradip_subject_groups.
# Subject table name: cheradip_subject (singular).

import json
from collections import defaultdict

from django.db import migrations, models

SUBJECT_TABLE = 'cheradip_subject'


def copy_m2m_to_group_codes(apps, schema_editor):
    """Copy subject_id -> [group_id, ...] from cheradip_subject_groups into cheradip_subject.group_codes.
    Skip when cheradip_subject_groups doesn't exist (fresh or out-of-sync DB).
    """
    conn = schema_editor.connection
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject_groups'
        """)
        if not cur.fetchone():
            return
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM cheradip_subject_groups')
        rows = cur.fetchall()
    # First column = subject pk (subject_code), second = group pk (group_code)
    by_subject = defaultdict(list)
    for row in rows:
        by_subject[row[0]].append(row[1])
    with conn.cursor() as cur:
        for sub_pk, codes in by_subject.items():
            cur.execute(
                f'UPDATE {SUBJECT_TABLE} SET group_codes = %s WHERE subject_code = %s',
                [json.dumps(codes), sub_pk]
            )


def noop(apps, schema_editor):
    pass


def add_group_codes_if_missing(apps, schema_editor):
    """Add group_codes to cheradip_subject only if table exists and column doesn't (idempotent)."""
    conn = schema_editor.connection
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = %s
        """, [SUBJECT_TABLE])
        if not cur.fetchone():
            return
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = %s AND COLUMN_NAME = 'group_codes'
        """, [SUBJECT_TABLE])
        if cur.fetchone():
            return  # already exists
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {SUBJECT_TABLE} ADD COLUMN group_codes JSON NULL")


def drop_subject_groups_if_exists(apps, schema_editor):
    """Drop cheradip_subject_groups only if it exists (idempotent)."""
    conn = schema_editor.connection
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject_groups'
        """)
        if not cur.fetchone():
            return
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS cheradip_subject_groups")


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0016_customer_teacher_level_subject_dept'),
    ]

    operations = [
        # Use cheradip_subject (singular); state-only so AddField/RemoveField target that table
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterModelTable('subject', 'cheradip_subject'),
            ],
            database_operations=[migrations.RunPython(noop, noop)],
        ),
        # Add group_codes only if missing (avoids "Duplicate column" when re-running)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='subject',
                    name='group_codes',
                    field=models.JSONField(blank=True, default=list, help_text='List of group codes, e.g. ["S","A","B"]'),
                ),
            ],
            database_operations=[migrations.RunPython(add_group_codes_if_missing, noop)],
        ),
        migrations.RunPython(copy_m2m_to_group_codes, noop),
        # Remove M2M "groups" from state; drop through table only if it exists
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='subject',
                    name='groups',
                ),
            ],
            database_operations=[
                migrations.RunPython(drop_subject_groups_if_exists, noop),
            ],
        ),
    ]
