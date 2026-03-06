"""
In cheradip_honours.cheradip_subject:
1. Remove duplicate rows (keep one per subject_name, subject_translated).
2. Set level = 'স্নাতক', level_tr = 'Honours', class_level = '13-16'; leave other columns unchanged.

Run:
  python manage.py normalize_honours_subject
  python manage.py normalize_honours_subject --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections

LEVEL_VALUE = 'স্নাতক'
LEVEL_TR_VALUE = 'Honours'
CLASS_LEVEL_VALUE = '13-16'


class Command(BaseCommand):
    help = 'Deduplicate honours cheradip_subject and set level, level_tr, class_level'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        conn = connections['honours']

        with conn.cursor() as cur:
            # Count before
            cur.execute("SELECT COUNT(*) FROM cheradip_subject")
            total_before = cur.fetchone()[0]

            # Count duplicates (rows that share subject_name, subject_translated with another row)
            cur.execute("""
                SELECT COUNT(*) FROM cheradip_subject s1
                WHERE EXISTS (
                    SELECT 1 FROM cheradip_subject s2
                    WHERE (s1.subject_name <=> s2.subject_name AND s1.subject_translated <=> s2.subject_translated AND s1.id > s2.id)
                )
            """)
            duplicate_count = cur.fetchone()[0]

            self.stdout.write('Rows before: %d. Duplicates to remove: %d.' % (total_before, duplicate_count))

            if not dry_run and duplicate_count > 0:
                # Delete duplicates: keep row with smallest id per (subject_name, subject_translated)
                cur.execute("""
                    DELETE s1 FROM cheradip_subject s1
                    INNER JOIN cheradip_subject s2
                    ON (s1.subject_name <=> s2.subject_name AND s1.subject_translated <=> s2.subject_translated AND s1.id > s2.id)
                """)
                self.stdout.write('Removed %d duplicate row(s).' % cur.rowcount)

            if not dry_run:
                cur.execute("""
                    UPDATE cheradip_subject
                    SET level = %s, level_tr = %s, class_level = %s
                """, [LEVEL_VALUE, LEVEL_TR_VALUE, CLASS_LEVEL_VALUE])
                self.stdout.write('Updated all rows: level=%r, level_tr=%r, class_level=%r.' % (LEVEL_VALUE, LEVEL_TR_VALUE, CLASS_LEVEL_VALUE))
            else:
                self.stdout.write('Would set level=%r, level_tr=%r, class_level=%r for all rows.' % (LEVEL_VALUE, LEVEL_TR_VALUE, CLASS_LEVEL_VALUE))

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cheradip_subject")
            total_after = cur.fetchone()[0]
        if not dry_run:
            self.stdout.write(self.style.SUCCESS('Done. Rows after: %d.' % total_after))
