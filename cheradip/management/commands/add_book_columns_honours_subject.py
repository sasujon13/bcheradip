"""
Add columns book_name and book_tr to cheradip_subject in the cheradip_honours database,
right after subject_tr.

Run:
  python manage.py add_book_columns_honours_subject
  python manage.py add_book_columns_honours_subject --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = 'Add book_name and book_tr to cheradip_subject (honours DB), after subject_tr'

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
            if cur.fetchone():
                self.stdout.write('Column book_name already exists in %s.cheradip_subject.' % db_name)
                return

            if dry_run:
                self.stdout.write('Would add book_name VARCHAR(255) NULL AFTER subject_tr.')
                self.stdout.write('Would add book_tr VARCHAR(255) NULL AFTER book_name.')
                return

            cur.execute(
                "ALTER TABLE cheradip_subject ADD COLUMN book_name VARCHAR(255) NULL AFTER subject_tr"
            )
            self.stdout.write('Added column book_name.')
            cur.execute(
                "ALTER TABLE cheradip_subject ADD COLUMN book_tr VARCHAR(255) NULL AFTER book_name"
            )
            self.stdout.write('Added column book_tr.')
            self.stdout.write(self.style.SUCCESS('Done. %s.cheradip_subject now has book_name and book_tr.' % db_name))
