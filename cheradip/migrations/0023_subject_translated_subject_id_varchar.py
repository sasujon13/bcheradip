# Ensure cheradip_subject_translated.subject_id is VARCHAR(12) to match Subject.id.
# Migration 0022 updated values but did not alter the column type; some DBs still have INT or short varchar.

from django.db import migrations


def subject_id_varchar(apps, schema_editor):
    conn = schema_editor.connection
    table = 'cheradip_subject_translated'
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_TYPE FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = %s AND COLUMN_NAME = 'subject_id'
        """, [table])
        row = cur.fetchone()
    if not row:
        return
    col_type = (row[0] or '').upper()
    if 'VARCHAR(12)' in col_type or col_type == 'VARCHAR(12)':
        return
    with conn.cursor() as cur:
        cur.execute("""
            SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE table_schema = DATABASE() AND table_name = %s
              AND COLUMN_NAME = 'subject_id' AND REFERENCED_TABLE_NAME IS NOT NULL
        """, [table])
        fk_row = cur.fetchone()
    fk_name = fk_row[0] if fk_row else None
    if fk_name:
        with conn.cursor() as cur:
            cur.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{fk_name}`")
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE `{table}` MODIFY COLUMN subject_id VARCHAR(12) NOT NULL")
    if fk_name:
        with conn.cursor() as cur:
            cur.execute(
                f"ALTER TABLE `{table}` ADD CONSTRAINT `{fk_name}` "
                f"FOREIGN KEY (subject_id) REFERENCES cheradip_subject(id) ON DELETE CASCADE"
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0022_subject_pk_country_code'),
    ]

    operations = [
        migrations.RunPython(subject_id_varchar, noop),
    ]
