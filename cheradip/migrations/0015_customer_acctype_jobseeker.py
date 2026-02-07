# Extend acctype to support 'JobSeeker' (max_length 7 -> 12).
# DB op is skipped when cheradip_customers doesn't exist (fresh or out-of-sync DB).

from django.db import migrations, models


def alter_acctype_if_table_exists(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_customers'
        """)
        if not cur.fetchone():
            return
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE cheradip_customers
            MODIFY COLUMN acctype VARCHAR(12) NOT NULL DEFAULT 'Student'
        """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0014_location_local_address'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='customer',
                    name='acctype',
                    field=models.CharField(
                        choices=[
                            ('Student', 'Student'),
                            ('Teacher', 'Teacher'),
                            ('JobSeeker', 'Job Seeker'),
                        ],
                        default='Student',
                        max_length=12,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(alter_acctype_if_table_exists, noop),
            ],
        ),
    ]
