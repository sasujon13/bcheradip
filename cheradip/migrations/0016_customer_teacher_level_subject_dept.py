# Add teacher_level, teacher_subject_code, teacher_department_code for Teacher signup.
# DB ops are skipped when cheradip_customers doesn't exist (fresh or out-of-sync DB).

from django.db import migrations, models


def add_teacher_fields_if_table_exists(apps, schema_editor):
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
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_customers'
        """)
        cols = {r[0] for r in cur.fetchall()}
    with conn.cursor() as cur:
        if 'teacher_level' not in cols:
            cur.execute("ALTER TABLE cheradip_customers ADD COLUMN teacher_level VARCHAR(12) NULL")
        if 'teacher_subject_code' not in cols:
            cur.execute("ALTER TABLE cheradip_customers ADD COLUMN teacher_subject_code VARCHAR(10) NULL")
        if 'teacher_department_code' not in cols:
            cur.execute("ALTER TABLE cheradip_customers ADD COLUMN teacher_department_code VARCHAR(20) NULL")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0015_customer_acctype_jobseeker'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='customer',
                    name='teacher_level',
                    field=models.CharField(blank=True, db_index=True, max_length=12, null=True),
                ),
                migrations.AddField(
                    model_name='customer',
                    name='teacher_subject_code',
                    field=models.CharField(blank=True, db_index=True, max_length=10, null=True),
                ),
                migrations.AddField(
                    model_name='customer',
                    name='teacher_department_code',
                    field=models.CharField(blank=True, db_index=True, max_length=20, null=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_teacher_fields_if_table_exists, noop),
            ],
        ),
    ]
