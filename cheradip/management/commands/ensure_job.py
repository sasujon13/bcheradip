"""
Ensure the job database (cheradip_job) has the expected NTRCA/job tables:

- cheradip_banbeis
- cheradip_institutes
- cheradip_merit5, cheradip_merit6, cheradip_merit7
- cheradip_recommend5, cheradip_recommend6, cheradip_recommend7
- cheradip_tokens
- cheradip_vacancy5, cheradip_vacancy6, cheradip_vacancy7

Runs migrate on the job database with --fake-initial. If a table already exists,
marks cheradip migrations as applied (--fake) and retries.

Usage:
  python manage.py ensure_job
  python manage.py ensure_job --check-only   # only verify, do not run migrate
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections

EXPECTED_JOB_TABLES = frozenset({
    'cheradip_banbeis',
    'cheradip_institutes',
    'cheradip_merit5',
    'cheradip_merit6',
    'cheradip_merit7',
    'cheradip_recommend5',
    'cheradip_recommend6',
    'cheradip_recommend7',
    'cheradip_tokens',
    'cheradip_vacancy5',
    'cheradip_vacancy6',
    'cheradip_vacancy7',
})


class Command(BaseCommand):
    help = 'Ensure job DB (cheradip_job) has banbeis, institutes, merit*, recommend*, tokens, vacancy* tables'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only verify tables exist; do not run migrate.',
        )

    def handle(self, *args, **options):
        if 'job' not in connections:
            self.stdout.write(self.style.ERROR('Database "job" is not configured.'))
            return

        conn = connections['job']
        db_name = conn.settings_dict['NAME']
        self.stdout.write('Database: %s' % db_name)

        if not options['check_only']:
            self.stdout.write('Running migrate on job database (--fake-initial)...')
            try:
                call_command('migrate', '--database=job', '--fake-initial', verbosity=1)
            except Exception as e:
                err_code = getattr(e, 'args', [None])[0] if getattr(e, 'args', None) else None
                err_str = str(e).lower()
                if err_code == 1050 or 'already exists' in err_str:
                    self.stdout.write(self.style.WARNING('Table(s) already exist; marking cheradip migrations as applied (--fake) and retrying...'))
                    call_command('migrate', 'cheradip', '--database=job', '--fake', verbosity=1)
                    try:
                        call_command('migrate', '--database=job', '--fake-initial', verbosity=1)
                    except Exception as e2:
                        self.stdout.write(self.style.ERROR('Migrate failed: %s' % e2))
                        return
                else:
                    self.stdout.write(self.style.ERROR('Migrate failed: %s' % e))
                    return

        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE'",
                [db_name],
            )
            existing = frozenset(row[0] for row in cur.fetchall())

        missing = EXPECTED_JOB_TABLES - existing
        present = EXPECTED_JOB_TABLES & existing

        if missing:
            self.stdout.write(self.style.WARNING('Missing tables (%d): %s' % (len(missing), ', '.join(sorted(missing)))))
        else:
            self.stdout.write(self.style.SUCCESS('All expected job tables present (%d).' % len(present)))

        if not missing:
            self.stdout.write(self.style.SUCCESS('Ensure job complete: %s.' % ', '.join(sorted(present))))
