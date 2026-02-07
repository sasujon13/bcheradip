# Subject PK: country_code + '_' + subject_code (e.g. BD_101).
# Add id, backfill, update FKs (chapter, mcq_ict, subject_translated), then make id the pk.

from django.db import migrations, models
import django.db.models.deletion


def subject_pk_to_country_code(apps, schema_editor):
    """Add id = country_id + '_' + subject_code, update FKs, then switch pk."""
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
    if 'id' in cols:
        # Already migrated (id exists as pk)
        return
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN id VARCHAR(12) NULL")
    with conn.cursor() as cur:
        cur.execute(f"""
            UPDATE {table} SET id = CONCAT(COALESCE(country_id,''), '_', subject_code)
            WHERE id IS NULL
        """)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_chapter'
        """)
        if cur.fetchone():
            cur.execute("""
                UPDATE cheradip_chapter c
                INNER JOIN cheradip_subject s ON c.subject_id = s.subject_code
                SET c.subject_id = s.id
            """)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_mcq_ict'
        """)
        if cur.fetchone():
            cur.execute("""
                UPDATE cheradip_mcq_ict m
                INNER JOIN cheradip_subject s ON m.subject_id = s.subject_code
                SET m.subject_id = s.id
            """)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.TABLES
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject_translated'
        """)
        if cur.fetchone():
            cur.execute("""
                UPDATE cheradip_subject_translated st
                INNER JOIN cheradip_subject s ON st.subject_id = s.subject_code
                SET st.subject_id = s.id
            """)
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {table} MODIFY subject_code VARCHAR(10) NOT NULL")
        cur.execute(f"ALTER TABLE {table} DROP PRIMARY KEY")
        cur.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id)")
        cur.execute(f"ALTER TABLE {table} ADD UNIQUE KEY uq_subject_country_code (country_id, subject_code)")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0021_subject_translated'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameField(model_name='subject', old_name='subject_code', new_name='subject_code_old'),
                migrations.AddField(
                    model_name='subject',
                    name='id',
                    field=models.CharField(max_length=12, primary_key=True, serialize=False, default='_'),
                ),
                migrations.RemoveField(model_name='subject', name='subject_code_old'),
                migrations.AddField(
                    model_name='subject',
                    name='subject_code',
                    field=models.CharField(db_index=True, max_length=10, default=''),
                ),
                migrations.AddConstraint(
                    model_name='subject',
                    constraint=models.UniqueConstraint(fields=('country', 'subject_code'), name='uq_subject_country_code'),
                ),
            ],
            database_operations=[
                migrations.RunPython(subject_pk_to_country_code, noop),
            ],
        ),
    ]
