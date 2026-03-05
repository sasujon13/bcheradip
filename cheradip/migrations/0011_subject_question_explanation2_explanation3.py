# Add explanation2 and explanation3 (TEXT) to all subject question tables.

from django.db import migrations


# Known cheradip tables that are NOT subject question tables (do not alter these)
NON_QUESTION_TABLES = {
    'cheradip_subject', 'cheradip_groups', 'cheradip_class_levels', 'cheradip_class_group_mappings',
    'cheradip_departments', 'cheradip_chapters', 'cheradip_topics', 'cheradip_country', 'cheradip_location',
    'cheradip_items', 'cheradip_transactions', 'cheradip_orderdetail', 'cheradip_order', 'cheradip_ordered',
    'cheradip_canceled', 'cheradip_customers', 'cheradip_customer_tokens', 'cheradip_notification',
    'cheradip_institutes', 'cheradip_years', 'cheradip_mcq_institutes', 'cheradip_mcq_years', 'cheradip_mcq_ict',
    'cheradip_tokens', 'cheradip_json_data', 'cheradip_order_orderdetails', 'cheradip_order_transaction',
    'cheradip_ordered_orderdetails', 'cheradip_ordered_transaction', 'cheradip_canceled_orderdetails',
    'cheradip_canceled_transaction',
}


def add_explanation_columns(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'cheradip_%'"
        )
        for (tname,) in cur.fetchall():
            if tname in NON_QUESTION_TABLES:
                continue
            try:
                cur.execute(f"ALTER TABLE `{tname}` ADD COLUMN explanation2 TEXT NULL AFTER explanation")
            except Exception:
                pass  # column may already exist
            try:
                cur.execute(f"ALTER TABLE `{tname}` ADD COLUMN explanation3 TEXT NULL AFTER explanation2")
            except Exception:
                pass


def remove_explanation_columns(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'cheradip_%'"
        )
        for (tname,) in cur.fetchall():
            if tname in NON_QUESTION_TABLES:
                continue
            for col in ('explanation3', 'explanation2'):
                try:
                    cur.execute(f"ALTER TABLE `{tname}` DROP COLUMN `{col}`")
                except Exception:
                    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0010_subject_question_tables'),
    ]

    operations = [
        migrations.RunPython(add_explanation_columns, remove_explanation_columns),
    ]
