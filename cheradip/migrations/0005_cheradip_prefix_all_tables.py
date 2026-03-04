# Rename all cheradip app tables to use cheradip_ prefix where missing.
# RunSQL renames existing DB tables; model Meta.db_table already updated in code.

from django.db import migrations


def rename_table_forward(apps, schema_editor):
    renames = [
        ('items', 'cheradip_items'),
        ('transactions', 'cheradip_transactions'),
        ('customer_tokens', 'cheradip_customer_tokens'),
        ('groups', 'cheradip_groups'),
        ('class_levels', 'cheradip_class_levels'),
        ('departments', 'cheradip_departments'),
        ('class_group_mappings', 'cheradip_class_group_mappings'),
        ('chapters', 'cheradip_chapters'),
        ('topics', 'cheradip_topics'),
        ('years', 'cheradip_years'),
        ('mcq_institutes', 'cheradip_mcq_institutes'),
        ('mcq_years', 'cheradip_mcq_years'),
        ('mcq_ict', 'cheradip_mcq_ict'),
        ('tokens', 'cheradip_tokens'),
        ('json_data', 'cheradip_json_data'),
    ]
    with schema_editor.connection.cursor() as cur:
        for old_name, new_name in renames:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
                [old_name],
            )
            if cur.fetchone():
                cur.execute(f"RENAME TABLE `{old_name}` TO `{new_name}`")


def rename_table_reverse(apps, schema_editor):
    renames = [
        ('items', 'cheradip_items'),
        ('transactions', 'cheradip_transactions'),
        ('customer_tokens', 'cheradip_customer_tokens'),
        ('groups', 'cheradip_groups'),
        ('class_levels', 'cheradip_class_levels'),
        ('departments', 'cheradip_departments'),
        ('class_group_mappings', 'cheradip_class_group_mappings'),
        ('chapters', 'cheradip_chapters'),
        ('topics', 'cheradip_topics'),
        ('years', 'cheradip_years'),
        ('mcq_institutes', 'cheradip_mcq_institutes'),
        ('mcq_years', 'cheradip_mcq_years'),
        ('mcq_ict', 'cheradip_mcq_ict'),
        ('tokens', 'cheradip_tokens'),
        ('json_data', 'cheradip_json_data'),
    ]
    with schema_editor.connection.cursor() as cur:
        for old_name, new_name in renames:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
                [new_name],
            )
            if cur.fetchone():
                cur.execute(f"RENAME TABLE `{new_name}` TO `{old_name}`")


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0004_remove_scraperpreset'),
    ]

    operations = [
        migrations.RunPython(rename_table_forward, rename_table_reverse),
    ]
