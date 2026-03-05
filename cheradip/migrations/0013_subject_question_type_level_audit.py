# Rename question_level -> type, add level (after type), add created_at, updated_at, updated_by (after subsource)
# on all subject question tables created by ensure_subject_question_tables.

from django.db import migrations


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


def alter_question_tables_forward(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'cheradip_%'"
        )
        for (tname,) in cur.fetchall():
            if tname in NON_QUESTION_TABLES:
                continue
            try:
                cur.execute(f"ALTER TABLE `{tname}` CHANGE COLUMN `question_level` `type` VARCHAR(100) NULL")
            except Exception:
                pass  # column may already be renamed or missing
            try:
                cur.execute(f"ALTER TABLE `{tname}` ADD COLUMN `level` VARCHAR(100) NULL AFTER `type`")
            except Exception:
                pass
            try:
                cur.execute(f"ALTER TABLE `{tname}` ADD COLUMN `created_at` DATETIME(6) NULL AFTER `subsource`")
            except Exception:
                pass
            try:
                cur.execute(f"ALTER TABLE `{tname}` ADD COLUMN `updated_at` DATETIME(6) NULL AFTER `created_at`")
            except Exception:
                pass
            try:
                cur.execute(f"ALTER TABLE `{tname}` ADD COLUMN `updated_by` VARCHAR(255) NULL AFTER `updated_at`")
            except Exception:
                pass


def alter_question_tables_reverse(apps, schema_editor):
    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'cheradip_%'"
        )
        for (tname,) in cur.fetchall():
            if tname in NON_QUESTION_TABLES:
                continue
            for col in ('updated_by', 'updated_at', 'created_at', 'level'):
                try:
                    cur.execute(f"ALTER TABLE `{tname}` DROP COLUMN `{col}`")
                except Exception:
                    pass
            try:
                cur.execute(f"ALTER TABLE `{tname}` CHANGE COLUMN `type` `question_level` VARCHAR(100) NULL")
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0012_dedupe_question_tables_by_class_subject'),
    ]

    operations = [
        migrations.RunPython(alter_question_tables_forward, alter_question_tables_reverse),
    ]
