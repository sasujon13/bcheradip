# Add reviewed_by_id to cheradip_pending_subject_request if table exists but column is missing
# (e.g. table was created by a partial run of 0014 before it was trimmed).

from django.db import migrations


def add_reviewed_by_if_missing(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_pending_subject_request'
            AND column_name = 'reviewed_by_id'
        """)
        if cur.fetchone()[0] > 0:
            return
        try:
            cur.execute("""
                ALTER TABLE cheradip_pending_subject_request
                ADD COLUMN reviewed_by_id bigint NULL
            """)
            cur.execute("""
                ALTER TABLE cheradip_pending_subject_request
                ADD CONSTRAINT fk_pending_subject_reviewed_by
                FOREIGN KEY (reviewed_by_id) REFERENCES cheradip_customers(id) ON DELETE SET NULL
            """)
        except Exception as e:
            if 'Duplicate column' in str(e) or '1060' in str(e):
                return
            raise


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0014_pending_subject_request'),
    ]

    operations = [
        migrations.RunPython(add_reviewed_by_if_missing, noop_reverse),
    ]
