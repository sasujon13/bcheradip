# Alter cheradip_subject: add country_id (FK to Country, as in Location), ensure level at beginning, rename group_codes -> group.

from django.db import migrations, models
import django.db.models.deletion


def alter_subject_table(apps, schema_editor):
    """Add country_id after level, rename group_codes to group. Idempotent."""
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
        if 'country_id' not in cols:
            # Add country_id after level; Country.pk is country_code (VARCHAR(2))
            cur.execute(f"ALTER TABLE {table} ADD COLUMN country_id VARCHAR(2) NULL AFTER level")
            cur.execute(f"""
                ALTER TABLE {table}
                ADD CONSTRAINT fk_subject_country
                FOREIGN KEY (country_id) REFERENCES cheradip_country(country_code) ON DELETE SET NULL
            """)
        if 'group_codes' in cols and 'group' not in cols:
            cur.execute(f"ALTER TABLE {table} CHANGE COLUMN group_codes `group` JSON NULL")
        elif 'group_codes' in cols and 'group' in cols:
            pass  # already renamed
        elif 'group' not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN `group` JSON NULL")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0018_subject_level'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='subject',
                    name='country',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='subjects',
                        to='cheradip.country',
                        db_index=True,
                    ),
                ),
                migrations.RenameField(
                    model_name='subject',
                    old_name='group_codes',
                    new_name='group',
                ),
                migrations.AlterField(
                    model_name='subject',
                    name='group',
                    field=models.JSONField(blank=True, db_column='group', default=list, help_text='List of group codes, e.g. ["S","A","B"]'),
                ),
            ],
            database_operations=[
                migrations.RunPython(alter_subject_table, noop),
            ],
        ),
    ]
