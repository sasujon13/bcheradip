# Replace post_office, post_code, road_house_no with local_address on Location.
# Idempotent: safe to run after apply_location_local_address.py (skips steps already done).

from django.db import migrations, models


def apply_local_address(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = 'cheradip_location'
        """)
        cols = {r[0] for r in cur.fetchall()}
    with conn.cursor() as cur:
        if 'local_address' not in cols:
            cur.execute("ALTER TABLE cheradip_location ADD COLUMN local_address VARCHAR(500) NULL")
        if 'road_house_no' in cols:
            cur.execute("UPDATE cheradip_location SET local_address = TRIM(road_house_no) WHERE road_house_no IS NOT NULL AND TRIM(road_house_no) != ''")
            cur.execute("ALTER TABLE cheradip_location DROP COLUMN road_house_no")
        if 'post_code' in cols:
            cur.execute("ALTER TABLE cheradip_location DROP COLUMN post_code")
        if 'post_office' in cols:
            cur.execute("ALTER TABLE cheradip_location DROP COLUMN post_office")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0013_location_post_office'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(apply_local_address, noop)],
            state_operations=[
                migrations.RemoveField(model_name='location', name='post_office'),
                migrations.RemoveField(model_name='location', name='post_code'),
                migrations.RemoveField(model_name='location', name='road_house_no'),
                migrations.AddField(
                    model_name='location',
                    name='local_address',
                    field=models.CharField(blank=True, max_length=500, null=True),
                ),
            ],
        ),
    ]
