# -*- coding: utf-8 -*-
# On SQLite, ensure cheradip_country exists. Migration 0009 renames countries -> cheradip_country
# using MySQL-only SQL; on SQLite the table may still be cheradip_countries. This migration
# renames cheradip_countries -> cheradip_country when on SQLite and cheradip_country is missing.

from django.db import migrations


def ensure_cheradip_country_sqlite(apps, schema_editor):
    """On SQLite, rename cheradip_countries or countries -> cheradip_country. Use inline SQL (no params) to avoid Django last_executed_query %-formatting."""
    conn = schema_editor.connection
    if conn.vendor != 'sqlite':
        return
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cheradip_country'")
        if cur.fetchone():
            return  # already correct
        for old_name in ('cheradip_countries', 'countries'):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='" + old_name.replace("'", "''") + "'")
            if cur.fetchone():
                cur.execute('ALTER TABLE "' + old_name.replace('"', '""') + '" RENAME TO cheradip_country')
                return


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0024_subject_tables_utf8mb4'),
    ]

    operations = [
        migrations.RunPython(ensure_cheradip_country_sqlite, noop),
    ]
