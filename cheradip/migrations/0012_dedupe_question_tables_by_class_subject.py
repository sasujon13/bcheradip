# One table per (class_level, subject_translated): keep first, drop duplicate tables.
# When level_tr differs but class_level and subject_translated are same, we keep the table for the first row and drop others.

import re
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

MYSQL_MAX_TABLE_NAME_LEN = 64


def _slug(s):
    if not s or not isinstance(s, str):
        return 'unknown'
    s = s.strip().lower().replace(' ', '_').replace('-', '_')
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s or 'unknown'


def table_name(level_tr, class_level, subject_translated):
    a = _slug(level_tr)[:12]
    b = _slug(class_level)[:8]
    c = _slug(subject_translated)[:36]
    name = f'cheradip_{a}_{b}_{c}'.rstrip('_')
    if len(name) > MYSQL_MAX_TABLE_NAME_LEN:
        name = name[:MYSQL_MAX_TABLE_NAME_LEN].rstrip('_')
    return name


def dedupe_keep_first_drop_rest(apps, schema_editor):
    """Keep one table per (class_level, subject_translated) — the one from the first row (by id). Drop all others."""
    Subject = apps.get_model('cheradip', 'Subject')
    # First row per (class_level, subject_translated) gives the table we keep
    seen_key = set()  # (class_level, subject_translated)
    tables_to_keep = set()
    for row in Subject.objects.order_by('id').values_list('level_tr', 'class_level', 'subject_translated'):
        level_tr = row[0] or ''
        class_level = row[1] or ''
        subject_translated = row[2] or ''
        key = (class_level, subject_translated)
        if key in seen_key:
            continue
        seen_key.add(key)
        name = table_name(level_tr, class_level, subject_translated)
        tables_to_keep.add(name)

    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'cheradip_%'"
        )
        to_drop = [
            tname for (tname,) in cur.fetchall()
            if tname not in NON_QUESTION_TABLES and tname not in tables_to_keep
        ]
        if to_drop:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for tname in to_drop:
                cur.execute(f"DROP TABLE IF EXISTS `{tname}`")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0011_subject_question_explanation2_explanation3'),
    ]

    operations = [
        migrations.RunPython(dedupe_keep_first_drop_rest, noop),
    ]
