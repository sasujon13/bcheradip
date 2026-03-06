"""
Set book_name = 'আইসিটি' and book_tr = 'ICT' for all rows in cheradip_subject
in the cheradip_honours database.

Run:
  python manage.py set_honours_subject_book_defaults
  python manage.py set_honours_subject_book_defaults --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "Set book_name='আইসিটি' and book_tr='ICT' for all rows in honours.cheradip_subject"

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        conn = connections['honours']
        db_name = conn.settings_dict['NAME']

        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = 'cheradip_subject' AND column_name = 'book_name'",
                [db_name]
            )
            if not cur.fetchone():
                self.stdout.write(self.style.ERROR('Column book_name not found in %s.cheradip_subject. Run add_book_columns_honours_subject first.' % db_name))
                return

            cur.execute("SELECT COUNT(*) FROM cheradip_subject")
            n = cur.fetchone()[0]

            if dry_run:
                self.stdout.write('Would update %d row(s): book_name=আইসিটি, book_tr=ICT.' % n)
                return

            cur.execute(
                "UPDATE cheradip_subject SET book_name = %s, book_tr = %s",
                ['আইসিটি', 'ICT']
            )
            self.stdout.write(self.style.SUCCESS('Updated %d row(s) in %s.cheradip_subject: book_name=আইসিটি, book_tr=ICT.' % (cur.rowcount, db_name)))
