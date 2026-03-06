"""
Rename column subject_translated to subject_tr in cheradip_subject
in both cheradip_honours and cheradip_hsc databases.

Run:
  python manage.py rename_subject_translated_to_subject_tr
  python manage.py rename_subject_translated_to_subject_tr --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections

# Match Subject.model: subject_translated CharField(max_length=255, blank=True, null=True)
ALTER_SQL = "ALTER TABLE cheradip_subject CHANGE COLUMN subject_translated subject_tr VARCHAR(255) NULL"


class Command(BaseCommand):
    help = 'Rename subject_translated to subject_tr in cheradip_subject (honours and hsc DBs)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        for db_alias in ('honours', 'hsc'):
            conn = connections[db_alias]
            db_name = conn.settings_dict['NAME']
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = 'cheradip_subject' AND column_name = 'subject_translated'",
                    [db_name]
                )
                if not cur.fetchone():
                    self.stdout.write('Column subject_translated not found in %s.cheradip_subject (already renamed?).' % db_name)
                    continue
                if dry_run:
                    self.stdout.write('Would run: %s on %s' % (ALTER_SQL, db_name))
                else:
                    cur.execute(ALTER_SQL)
                    self.stdout.write(self.style.SUCCESS('Renamed subject_translated -> subject_tr in %s.cheradip_subject.' % db_name))
