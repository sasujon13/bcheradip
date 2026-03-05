"""
Re-read cheradip_subject and rebuild subject question tables.
Use after changing subject_translated (or other subject data) so table names and set match current data.
- Drops all existing subject question tables.
- Creates one table per (class_level, subject_translated) using first row (by id); full schema including explanation2, explanation3.
"""
import re
from django.core.management.base import BaseCommand
from django.db import connection


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

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS `{table_name}` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subject VARCHAR(255) NULL,
    chapter_no VARCHAR(50) NULL,
    chapter VARCHAR(255) NULL,
    topic VARCHAR(255) NULL,
    question TEXT NULL,
    option_1 VARCHAR(500) NULL,
    option_2 VARCHAR(500) NULL,
    option_3 VARCHAR(500) NULL,
    option_4 VARCHAR(500) NULL,
    answer VARCHAR(500) NULL,
    explanation TEXT NULL,
    explanation2 TEXT NULL,
    explanation3 TEXT NULL,
    type VARCHAR(100) NULL,
    level VARCHAR(100) NULL,
    subsource VARCHAR(255) NULL,
    created_at DATETIME(6) NULL,
    updated_at DATETIME(6) NULL,
    updated_by VARCHAR(255) NULL
)
"""


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


class Command(BaseCommand):
    help = 'Re-read cheradip_subject and rebuild subject question tables (drop existing, create from current data)'

    def handle(self, *args, **options):
        from cheradip.models import Subject

        with connection.cursor() as cur:
            # 1) Drop all existing subject question tables
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'cheradip_%'"
            )
            to_drop = [
                tname for (tname,) in cur.fetchall()
                if tname not in NON_QUESTION_TABLES
            ]
            if to_drop:
                cur.execute("SET FOREIGN_KEY_CHECKS = 0")
                for tname in to_drop:
                    cur.execute(f"DROP TABLE IF EXISTS `{tname}`")
                    self.stdout.write(f'Dropped {tname}')
                cur.execute("SET FOREIGN_KEY_CHECKS = 1")
                self.stdout.write(self.style.WARNING(f'Dropped {len(to_drop)} question tables.'))
            else:
                self.stdout.write('No existing question tables to drop.')

            # 2) Create one table per (class_level, subject_translated), first row by id
            seen_key = set()
            created = 0
            for row in Subject.objects.order_by('id').values_list('level_tr', 'class_level', 'subject_translated'):
                level_tr = row[0] or ''
                class_level = row[1] or ''
                subject_translated = row[2] or ''
                key = (class_level, subject_translated)
                if key in seen_key:
                    continue
                seen_key.add(key)
                name = table_name(level_tr, class_level, subject_translated)
                cur.execute(CREATE_TABLE_SQL.format(table_name=name))
                created += 1
                self.stdout.write(f'Created {name}')

        self.stdout.write(self.style.SUCCESS(f'Rebuild complete: {created} question tables created from current cheradip_subject.'))
