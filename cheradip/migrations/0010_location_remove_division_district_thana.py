# Generated manually for Location refactor: drop Division/District/Thana, add Location
# DB changes are conditional (skip when tables don't exist) so migration works on incomplete DBs

from django.db import migrations, models
import django.db.models.deletion


def _apply_location_changes_mysql(cursor):
    """MySQL implementation."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cheradip_location (
            id INT AUTO_INCREMENT PRIMARY KEY,
            country VARCHAR(60) NULL,
            division VARCHAR(100) NULL,
            district VARCHAR(100) NULL,
            thana VARCHAR(100) NULL,
            post_code VARCHAR(20) NULL,
            road_house_no VARCHAR(255) NULL,
            INDEX (country),
            INDEX (division),
            INDEX (district),
            INDEX (thana),
            INDEX (division, district)
        )
    """)
    addr_tables = ['cheradip_customers', 'cheradip_orders', 'cheradip_ordered', 'cheradip_canceled']
    old_cols = ['country', 'division', 'district', 'thana', 'union', 'village']
    for table in addr_tables:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
            [table],
        )
        if not cursor.fetchone():
            continue
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s AND column_name = 'location_id'",
            [table],
        )
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN location_id INT NULL")
            try:
                cursor.execute(
                    f"ALTER TABLE `{table}` ADD CONSTRAINT fk_{table}_location "
                    f"FOREIGN KEY (location_id) REFERENCES cheradip_location(id)"
                )
            except Exception:
                pass
        for col in old_cols:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
                [table, col],
            )
            if cursor.fetchone():
                try:
                    cursor.execute(f"ALTER TABLE `{table}` DROP COLUMN `{col}`")
                except Exception:
                    pass
    tables_to_drop = ['cheradip_thanas', 'cheradip_districts', 'cheradip_divisions', 'cheradip_division', 'cheradip_district']
    for ref_table in tables_to_drop:
        cursor.execute(
            "SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME = %s",
            [ref_table],
        )
        for (child_table, fk_name) in cursor.fetchall():
            try:
                cursor.execute(f"ALTER TABLE `{child_table}` DROP FOREIGN KEY `{fk_name}`")
            except Exception:
                pass
    for t in tables_to_drop:
        cursor.execute(f"DROP TABLE IF EXISTS `{t}`")


def _apply_location_changes_sqlite(cursor):
    """SQLite implementation: no inline INDEX, use CREATE INDEX; use pragma/sqlite_master.
    Uses inline SQL (no params) to avoid Django's last_executed_query %-formatting on params."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cheradip_location (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country VARCHAR(60) NULL,
            division VARCHAR(100) NULL,
            district VARCHAR(100) NULL,
            thana VARCHAR(100) NULL,
            post_code VARCHAR(20) NULL,
            road_house_no VARCHAR(255) NULL
        )
    """)
    for idx_name, cols in [
        ('cheradip_location_country_idx', ['country']),
        ('cheradip_location_division_idx', ['division']),
        ('cheradip_location_district_idx', ['district']),
        ('cheradip_location_thana_idx', ['thana']),
        ('cheradip_location_division_district_idx', ['division', 'district']),
    ]:
        safe_name = idx_name.replace("'", "''")
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='" + safe_name + "'")
        if not cursor.fetchone():
            q = idx_name.replace('"', '""')
            cursor.execute('CREATE INDEX "' + q + '" ON cheradip_location (' + ', '.join('"' + c.replace('"', '""') + '"' for c in cols) + ')')

    addr_tables = ['cheradip_customers', 'cheradip_orders', 'cheradip_ordered', 'cheradip_canceled']
    old_cols = ['country', 'division', 'district', 'thana', 'union', 'village']
    for table in addr_tables:
        safe_table_str = table.replace("'", "''")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='" + safe_table_str + "'")
        if not cursor.fetchone():
            continue
        qtable = table.replace('"', '""')
        cursor.execute('PRAGMA table_info("' + qtable + '")')
        col_names = [row[1] for row in cursor.fetchall()]
        if 'location_id' not in col_names:
            cursor.execute('ALTER TABLE "' + qtable + '" ADD COLUMN location_id INTEGER NULL')
        for col in old_cols:
            if col in col_names:
                try:
                    qcol = col.replace('"', '""')
                    cursor.execute('ALTER TABLE "' + qtable + '" DROP COLUMN "' + qcol + '"')
                except Exception:
                    pass  # SQLite < 3.35.0 does not support DROP COLUMN

    for t in ['cheradip_thanas', 'cheradip_districts', 'cheradip_divisions', 'cheradip_division', 'cheradip_district']:
        cursor.execute('DROP TABLE IF EXISTS "' + t.replace('"', '""') + '"')


def apply_location_changes(apps, schema_editor):
    """Create cheradip_location, add location_id to customer/order/ordered/canceled if tables exist, drop division/district/thana tables."""
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == 'sqlite':
            _apply_location_changes_sqlite(cursor)
        else:
            _apply_location_changes_mysql(cursor)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0009_rename_banbeis_eiin_cf994f_idx_cheradip_ba_eiin_d0c2a3_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(apply_location_changes, noop_reverse),
        # State-only: tell Django about Location model and updated Customer/Order/Ordered/Canceled, removed Division/District/Thana
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Location',
                    fields=[
                        ('id', models.AutoField(primary_key=True, serialize=False)),
                        ('country', models.CharField(blank=True, db_index=True, max_length=60, null=True)),
                        ('division', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                        ('district', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                        ('thana', models.CharField(blank=True, db_index=True, max_length=100, null=True)),
                        ('post_code', models.CharField(blank=True, max_length=20, null=True)),
                        ('road_house_no', models.CharField(blank=True, max_length=255, null=True)),
                    ],
                    options={'db_table': 'cheradip_location', 'ordering': ['country', 'division', 'district', 'thana']},
                ),
                migrations.AddField(
                    model_name='customer',
                    name='location',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customers', to='cheradip.location', db_index=True),
                ),
                migrations.RemoveField(model_name='customer', name='country'),
                migrations.RemoveField(model_name='customer', name='division'),
                migrations.RemoveField(model_name='customer', name='district'),
                migrations.RemoveField(model_name='customer', name='thana'),
                migrations.RemoveField(model_name='customer', name='union'),
                migrations.RemoveField(model_name='customer', name='village'),
                migrations.AddField(
                    model_name='order',
                    name='location',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='cheradip.location', db_index=True),
                ),
                migrations.RemoveField(model_name='order', name='division'),
                migrations.RemoveField(model_name='order', name='district'),
                migrations.RemoveField(model_name='order', name='thana'),
                migrations.RemoveField(model_name='order', name='union'),
                migrations.RemoveField(model_name='order', name='village'),
                migrations.AddField(
                    model_name='ordered',
                    name='location',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ordered', to='cheradip.location', db_index=True),
                ),
                migrations.RemoveField(model_name='ordered', name='division'),
                migrations.RemoveField(model_name='ordered', name='district'),
                migrations.RemoveField(model_name='ordered', name='thana'),
                migrations.RemoveField(model_name='ordered', name='union'),
                migrations.RemoveField(model_name='ordered', name='village'),
                migrations.AddField(
                    model_name='canceled',
                    name='location',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cancelled_orders', to='cheradip.location', db_index=True),
                ),
                migrations.RemoveField(model_name='canceled', name='division'),
                migrations.RemoveField(model_name='canceled', name='district'),
                migrations.RemoveField(model_name='canceled', name='thana'),
                migrations.RemoveField(model_name='canceled', name='union'),
                migrations.RemoveField(model_name='canceled', name='village'),
                migrations.DeleteModel(name='Thana'),
                migrations.DeleteModel(name='District'),
                migrations.DeleteModel(name='Division'),
            ],
            database_operations=[],
        ),
    ]
