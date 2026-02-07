# -*- coding: utf-8 -*-
# Ensure cheradip_subject and cheradip_subject_translated use utf8mb4 so Bengali/Unicode
# stays correct when exporting CSV or SQL. Run after 0023.

from django.db import migrations


def tables_utf8mb4(apps, schema_editor):
    conn = schema_editor.connection
    for table in ('cheradip_subject', 'cheradip_subject_translated'):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_COLLATION FROM information_schema.TABLES
                WHERE table_schema = DATABASE() AND table_name = %s
            """, [table])
            row = cur.fetchone()
        if not row or (row[0] or '').lower().startswith('utf8mb4'):
            continue
        with conn.cursor() as cur:
            cur.execute(
                f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0023_subject_translated_subject_id_varchar'),
    ]

    operations = [
        migrations.RunPython(tables_utf8mb4, noop),
    ]
