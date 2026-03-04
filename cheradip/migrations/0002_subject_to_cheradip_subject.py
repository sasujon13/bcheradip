# Migration: subjects -> cheradip_subject; Chapter/Mcq_ict use subject_code instead of subject FK

import django.db.models.deletion
from django.db import migrations, models


def copy_subjects_to_cheradip_subject(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'subjects'")
        if not cur.fetchone():
            return
        cur.execute("SELECT 1 FROM cheradip_subject LIMIT 1")
        if cur.fetchone():
            return  # already copied
        cur.execute("""
            INSERT INTO cheradip_subject (subject_code, subject_name, subject_translated, created_at, updated_at)
            SELECT subject_code, subject_name, COALESCE(subject_name_tr, subject_name), created_at, updated_at
            FROM subjects
        """)


def chapter_backfill_subject_code(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("UPDATE chapters SET subject_code = subject_id WHERE subject_id IS NOT NULL AND subject_id != ''")


def mcq_backfill_subject_code(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("UPDATE mcq_ict SET subject_code = subject_id WHERE subject_id IS NOT NULL AND subject_id != ''")


def drop_fk_and_column(schema_editor, table, column):
    """Drop FK, then indexes on the column, then column for MySQL. No-op if column already gone."""
    with schema_editor.connection.cursor() as cur:
        if not _column_exists(cur, table, column):
            return
        # Drop FK first
        cur.execute(
            """
            SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            [table, column],
        )
        row = cur.fetchone()
        if row:
            fk_name = row[0]
            cur.execute(f"ALTER TABLE {schema_editor.quote_name(table)} DROP FOREIGN KEY {schema_editor.quote_name(fk_name)}")
        # Drop indexes that use this column (MySQL 1072 can occur when index references column)
        cur.execute(
            """
            SELECT INDEX_NAME FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            AND INDEX_NAME != 'PRIMARY'
            """,
            [table, column],
        )
        for (idx_name,) in cur.fetchall():
            cur.execute(f"ALTER TABLE {schema_editor.quote_name(table)} DROP INDEX {schema_editor.quote_name(idx_name)}")
        cur.execute(f"ALTER TABLE {schema_editor.quote_name(table)} DROP COLUMN {schema_editor.quote_name(column)}")


def drop_chapter_subject(apps, schema_editor):
    drop_fk_and_column(schema_editor, "chapters", "subject_id")


def drop_mcq_subject(apps, schema_editor):
    drop_fk_and_column(schema_editor, "mcq_ict", "subject_id")


def _column_exists(cursor, table, column):
    cursor.execute(
        "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        [table, column],
    )
    return cursor.fetchone() is not None


def _chapter_subject_code_forward(schema_editor):
    with schema_editor.connection.cursor() as cur:
        if not _column_exists(cur, "chapters", "subject_code"):
            cur.execute("ALTER TABLE chapters ADD COLUMN subject_code VARCHAR(12) NULL")
        cur.execute("UPDATE chapters SET subject_code = subject_id WHERE subject_id IS NOT NULL AND subject_id != '' AND (subject_code IS NULL OR subject_code = '')")
        cur.execute("ALTER TABLE chapters MODIFY COLUMN subject_code VARCHAR(12) NOT NULL")
    drop_chapter_subject(None, schema_editor)


def _mcq_subject_code_forward(schema_editor):
    with schema_editor.connection.cursor() as cur:
        if not _column_exists(cur, "mcq_ict", "subject_code"):
            cur.execute("ALTER TABLE mcq_ict ADD COLUMN subject_code VARCHAR(12) NULL")
        cur.execute("UPDATE mcq_ict SET subject_code = subject_id WHERE subject_id IS NOT NULL AND subject_id != '' AND (subject_code IS NULL OR subject_code = '')")
        cur.execute("ALTER TABLE mcq_ict MODIFY COLUMN subject_code VARCHAR(12) NOT NULL")
    drop_mcq_subject(None, schema_editor)


# MySQL: create cheradip_subject (new schema)
CREATE_CHERADIP_SUBJECT = """
CREATE TABLE IF NOT EXISTS cheradip_subject (
    id INT AUTO_INCREMENT PRIMARY KEY,
    level VARCHAR(100) NULL,
    level_tr VARCHAR(100) NULL,
    groups JSON NULL,
    class_level INT NULL,
    subject_name VARCHAR(255) NULL,
    subject_translated VARCHAR(255) NULL,
    subject_code VARCHAR(12) NOT NULL,
    country_id VARCHAR(2) NULL,
    language_code VARCHAR(10) NULL,
    created_at DATETIME(6) NULL,
    updated_at DATETIME(6) NULL,
    INDEX (subject_code),
    INDEX (country_id),
    INDEX (country_id, level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

DROP_SUBJECT_GROUPS = "DROP TABLE IF EXISTS subject_groups;"
DROP_SUBJECTS = "DROP TABLE IF EXISTS subjects;"


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0001_initial'),
    ]

    operations = [
        # --- Subject: replace state and DB ---
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='Subject'),
                migrations.CreateModel(
                    name='Subject',
                    fields=[
                        ('id', models.AutoField(primary_key=True, serialize=False)),
                        ('level', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                        ('level_tr', models.CharField(blank=True, max_length=100, null=True)),
                        ('groups', models.JSONField(blank=True, help_text='JSON array of group names/codes', null=True)),
                        ('class_level', models.IntegerField(blank=True, null=True)),
                        ('subject_name', models.CharField(blank=True, max_length=255, null=True)),
                        ('subject_translated', models.CharField(blank=True, max_length=255, null=True)),
                        ('subject_code', models.CharField(db_index=True, max_length=12)),
                        ('country_id', models.CharField(blank=True, db_index=True, max_length=2, null=True)),
                        ('language_code', models.CharField(blank=True, db_index=True, max_length=10, null=True)),
                        ('created_at', models.DateTimeField(blank=True, auto_now_add=True, null=True)),
                        ('updated_at', models.DateTimeField(blank=True, auto_now=True, null=True)),
                    ],
                    options={'db_table': 'cheradip_subject', 'ordering': ['subject_code', 'level', 'country_id']},
                ),
            ],
            database_operations=[
                migrations.RunSQL(CREATE_CHERADIP_SUBJECT, migrations.RunSQL.noop),
                migrations.RunPython(copy_subjects_to_cheradip_subject, migrations.RunPython.noop),
            ],
        ),
        # --- Chapter: subject_id -> subject_code (idempotent) ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    lambda apps, se: _chapter_subject_code_forward(se),
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(model_name='chapter', name='subject_code', field=models.CharField(db_index=True, max_length=12, null=True)),
                migrations.AlterField(model_name='chapter', name='subject_code', field=models.CharField(db_index=True, max_length=12)),
                migrations.RemoveField(model_name='chapter', name='subject'),
                migrations.AlterUniqueTogether(name='chapter', unique_together={('subject_code', 'chapter_no')}),
                migrations.AddIndex(model_name='chapter', index=models.Index(fields=['subject_code', 'chapter_no'], name='chapters_subject_code_idx')),
            ],
        ),
        # --- Mcq_ict: subject_id -> subject_code (idempotent) ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    lambda apps, se: _mcq_subject_code_forward(se),
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(model_name='mcq_ict', name='subject_code', field=models.CharField(db_index=True, max_length=12, null=True)),
                migrations.AlterField(model_name='mcq_ict', name='subject_code', field=models.CharField(db_index=True, max_length=12)),
                migrations.RemoveField(model_name='mcq_ict', name='subject'),
                migrations.AddIndex(model_name='mcq_ict', index=models.Index(fields=['subject_code', 'chapter', 'topic'], name='mcq_ict_subject_code_idx')),
            ],
        ),
        # --- Drop old tables ---
        migrations.RunSQL(DROP_SUBJECT_GROUPS, migrations.RunSQL.noop),
        migrations.RunSQL(DROP_SUBJECTS, migrations.RunSQL.noop),
    ]
