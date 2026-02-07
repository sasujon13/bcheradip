# Add level column at the beginning of cheradip_subject.

from django.db import migrations, models


def add_level_if_missing(apps, schema_editor):
    """Add level as first column when table exists and column doesn't (idempotent)."""
    conn = schema_editor.connection
    table = 'cheradip_subject'
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = %s
        """, [table])
        if not cur.fetchone():
            return
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = %s AND COLUMN_NAME = 'level'
        """, [table])
        if cur.fetchone():
            return
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN level VARCHAR(20) NULL FIRST")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0017_subject_group_codes_drop_subject_groups'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='subject',
                    name='level',
                    field=models.CharField(blank=True, db_index=True, max_length=20, null=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_level_if_missing, noop),
            ],
        ),
    ]
