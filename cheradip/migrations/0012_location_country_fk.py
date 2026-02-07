# Location.country: CharField -> FK to cheradip_country(country_code).
# Country uses country_code as PK (no integer id).

from django.db import migrations, models
import django.db.models.deletion


def location_country_to_fk(apps, schema_editor):
    """Add country_id FK, backfill from country (text), drop country."""
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() "
            "AND table_name = 'cheradip_location' AND column_name = 'country_id'"
        )
        if cursor.fetchone():
            return  # already migrated
        cursor.execute(
            "ALTER TABLE cheradip_location ADD COLUMN country_id VARCHAR(2) NULL"
        )
        cursor.execute("""
            UPDATE cheradip_location L
            SET L.country_id = (
                SELECT C.country_code FROM cheradip_country C
                WHERE C.country_name = L.country OR C.country_code = L.country
                LIMIT 1
            )
        """)
        cursor.execute("ALTER TABLE cheradip_location DROP COLUMN country")
        cursor.execute("""
            ALTER TABLE cheradip_location
            ADD CONSTRAINT fk_location_country
            FOREIGN KEY (country_id) REFERENCES cheradip_country(country_code)
        """)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0011_country_time_display_flag_lang'),
    ]

    operations = [
        migrations.RunPython(location_country_to_fk, noop_reverse),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='location', name='country'),
                migrations.AddField(
                    model_name='location',
                    name='country',
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='locations',
                        to='cheradip.country',
                        db_index=True,
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
