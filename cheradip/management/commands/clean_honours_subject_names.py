"""
In cheradip_honours.cheradip_subject:
1. Remove "১ম পত্র" and "২য় পত্র" from subject_name (then trim).
2. Remove "1st paper", "1st Paper", "2nd paper", "2nd Paper" from subject_translated (then trim).
3. Set groups to empty (NULL).
4. Keep only unique rows by (subject_name, subject_translated).

Run:
  python manage.py clean_honours_subject_names
  python manage.py clean_honours_subject_names --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = 'Clean subject_name/subject_translated (remove ১ম পত্র/২য় পত্র, 1st/2nd paper), clear groups, deduplicate'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        conn = connections['honours']

        with conn.cursor() as cur:
            if dry_run:
                cur.execute("SELECT id, subject_name, subject_translated FROM cheradip_subject LIMIT 5")
                for row in cur.fetchall():
                    self.stdout.write('  Sample before: id=%s subject_name=%r subject_translated=%r' % row)
                self.stdout.write('Would: strip "১ম পত্র"/"২য় পত্র" from subject_name, "1st paper"/"2nd Paper" from subject_translated, set groups=NULL, then deduplicate.')
                return

            # 1) Remove "১ম পত্র" and "২য় পত্র" from subject_name, trim
            cur.execute("""
                UPDATE cheradip_subject
                SET subject_name = TRIM(BOTH ',' FROM TRIM(REPLACE(REPLACE(COALESCE(subject_name, ''), '২য় পত্র', ''), '১ম পত্র', '')))
            """)
            self.stdout.write('Cleaned subject_name (removed ১ম পত্র, ২য় পত্র): %d rows updated.' % cur.rowcount)

            # 2) Remove "1st paper", "1st Paper", "2nd paper", "2nd Paper" from subject_translated, trim
            cur.execute("""
                UPDATE cheradip_subject
                SET subject_translated = TRIM(BOTH ',' FROM TRIM(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(subject_translated, ''),
                    '2nd Paper', ''), '2nd paper', ''), '1st Paper', ''), '1st paper', '')))
            """)
            self.stdout.write('Cleaned subject_translated (removed 1st/2nd paper): %d rows updated.' % cur.rowcount)

            # 3) Set groups to NULL
            cur.execute("UPDATE cheradip_subject SET groups = NULL")
            self.stdout.write('Set groups to NULL for all rows.')

            # 4) Delete duplicates: keep one per (subject_name, subject_translated) with smallest id
            cur.execute("""
                DELETE s1 FROM cheradip_subject s1
                INNER JOIN cheradip_subject s2
                ON (s1.subject_name <=> s2.subject_name AND s1.subject_translated <=> s2.subject_translated AND s1.id > s2.id)
            """)
            removed = cur.rowcount
            self.stdout.write('Removed %d duplicate row(s).' % removed)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cheradip_subject")
            n = cur.fetchone()[0]
        self.stdout.write(self.style.SUCCESS('Done. Rows remaining: %d.' % n))
