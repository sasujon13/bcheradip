"""
Ensure the default database (cheradip_cheradip) has core tables only.

This command operates ONLY on cheradip_cheradip (default). It does not create or
modify tables in cheradip_job, cheradip_hsc, or cheradip_honours; those are
handled by ensure_job, ensure_hsc, and ensure_honours.

Tables ensured on default DB (only these; no job/hsc/honours tables):
- cheradip_country, cheradip_location, cheradip_customers, cheradip_customer_tokens
- cheradip_items, cheradip_transactions, cheradip_orderdetail
- cheradip_notification, cheradip_json_data
- Django: django_migrations, django_content_type, django_session, auth_*, etc.

Runs migrate with --database=default only (--fake-initial so existing tables are skipped).

Usage:
  python manage.py ensure_cheradip
  python manage.py ensure_cheradip --check-only   # only verify, do not run migrate
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

# Only ever run migrate on the default database (cheradip_cheradip).
DEFAULT_DB_ALIAS = 'default'

# Tables we expect on default DB only (no job/hsc/honours tables here)
EXPECTED_CORE_TABLES = frozenset({
    'cheradip_country',
    'cheradip_location',
    'cheradip_customers',
    'cheradip_items',
    'cheradip_transactions',
    'cheradip_orderdetail',
    'cheradip_notification',
    'cheradip_json_data',
    'cheradip_customer_tokens',
    'django_migrations',
    'django_content_type',
    'django_session',
    'django_admin_log',
    'auth_group',
    'auth_permission',
    'auth_group_permissions',
    'cheradip_customer_user_permissions',
    'cheradip_customer_groups',
})
EXPECTED_OPTIONAL = frozenset()


class Command(BaseCommand):
    help = (
        'Ensure cheradip_cheradip (default) has core tables only. '
        'Does not create job/hsc/honours tables (use ensure_job, ensure_hsc, ensure_honours).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only verify tables exist; do not run migrate.',
        )

    def handle(self, *args, **options):
        if connection.alias != DEFAULT_DB_ALIAS:
            self.stdout.write(self.style.ERROR(
                'ensure_cheradip must run with the default database. Current alias: %s' % connection.alias
            ))
            return
        db_name = connection.settings_dict['NAME']
        self.stdout.write('Database: %s (default only; not job/hsc/honours)' % db_name)

        if not options['check_only']:
            self.stdout.write(
                'Running migrate on default database only (--database=%s, --fake-initial)...'
                % DEFAULT_DB_ALIAS
            )
            try:
                call_command('migrate', '--database=%s' % DEFAULT_DB_ALIAS, '--fake-initial', verbosity=1)
            except Exception as e:
                err_code = getattr(e, 'args', [None])[0] if getattr(e, 'args', None) else None
                err_str = str(e).lower()
                if err_code == 1050 or 'already exists' in err_str:
                    self.stdout.write(self.style.WARNING('Table(s) already exist; marking cheradip migrations as applied (--fake) and retrying...'))
                    call_command('migrate', 'cheradip', '--database=%s' % DEFAULT_DB_ALIAS, '--fake', verbosity=1)
                    try:
                        call_command('migrate', '--database=%s' % DEFAULT_DB_ALIAS, '--fake-initial', verbosity=1)
                    except Exception as e2:
                        self.stdout.write(self.style.ERROR('Migrate failed: %s' % e2))
                        return
                else:
                    self.stdout.write(self.style.ERROR('Migrate failed: %s' % e))
                    return

        with connection.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE'",
                [db_name],
            )
            existing = frozenset(row[0] for row in cur.fetchall())

        missing_core = EXPECTED_CORE_TABLES - existing
        missing_optional = EXPECTED_OPTIONAL - existing
        present_core = EXPECTED_CORE_TABLES & existing
        present_optional = EXPECTED_OPTIONAL & existing

        if missing_core:
            self.stdout.write(self.style.WARNING('Missing core tables (%d): %s' % (len(missing_core), ', '.join(sorted(missing_core)))))
        else:
            self.stdout.write(self.style.SUCCESS('All core tables present (%d).' % len(present_core)))

        if present_optional:
            self.stdout.write('Optional tables present: %s' % ', '.join(sorted(present_optional)))
        if missing_optional:
            self.stdout.write('Optional tables missing: %s' % ', '.join(sorted(missing_optional)))

        if missing_core and not options['check_only']:
            self.stdout.write(self.style.WARNING('Some core tables are still missing. Check migrations and run migrate again.'))

        if not missing_core:
            self.stdout.write(self.style.SUCCESS(
                'Ensure complete: country, location, customer, order/payment and Django tables are in place. '
                'Default Django user panel (auth, admin) is on cheradip_cheradip — use /admin/ to add users and assign activities.'
            ))
