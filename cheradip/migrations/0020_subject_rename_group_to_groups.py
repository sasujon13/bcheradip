# Rename Subject.group -> groups (avoid reserved word).

from django.db import migrations, models


def rename_group_to_groups(apps, schema_editor):
    """Rename cheradip_subject column `group` to groups. Idempotent."""
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
            WHERE table_schema = DATABASE() AND table_name = %s
        """, [table])
        cols = {r[0] for r in cur.fetchall()}
    with conn.cursor() as cur:
        if 'group' in cols and 'groups' not in cols:
            cur.execute(f"ALTER TABLE {table} CHANGE COLUMN `group` groups JSON NULL")
        elif 'groups' in cols:
            pass  # already renamed


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0019_subject_country_rename_group'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(
                    model_name='subject',
                    old_name='group',
                    new_name='groups',
                ),
                migrations.AlterField(
                    model_name='subject',
                    name='groups',
                    field=models.JSONField(blank=True, db_column='groups', default=list, help_text='List of group codes, e.g. ["S","A","B"]'),
                ),
            ],
            database_operations=[
                migrations.RunPython(rename_group_to_groups, noop),
            ],
        ),
    ]
