"""
Ensure the default database (cheradip_cheradip) has the Django user/admin panel tables.

Runs migrate --database=default so cheradip_cheradip gets:
- Django auth: auth_group, auth_permission, auth_group_permissions
- User model: cheradip_customers (Customer = AUTH_USER_MODEL)
- User–auth links: cheradip_customer_groups, cheradip_customer_user_permissions
- Admin: django_content_type, django_session, django_admin_log

After this you can open /admin/, add users (Customers), and assign groups/permissions.
All user management uses the cheradip_cheradip database.

Usage:
  python manage.py ensure_default_user_panel
  python manage.py ensure_default_user_panel --createsuperuser   # prompt to create admin user
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings

DEFAULT_DB_ALIAS = 'default'


class Command(BaseCommand):
    help = (
        'Ensure cheradip_cheradip (default DB) has Django user panel tables (auth, admin, Customer). '
        'Run this to add/set up the default Django user management on the default database.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--createsuperuser',
            action='store_true',
            help='After migrate, run createsuperuser to add an admin user (Customer).',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only verify tables exist; do not run migrate.',
        )

    def handle(self, *args, **options):
        if connection.alias != DEFAULT_DB_ALIAS:
            self.stdout.write(self.style.WARNING(
                'This command uses the default database. Current alias: %s' % connection.alias
            ))
        db_name = connection.settings_dict.get('NAME', '')
        self.stdout.write('Default database (Django user panel): %s' % db_name)

        if not options['check_only']:
            self.stdout.write('Running migrate on default database...')
            try:
                call_command('migrate', '--database=%s' % DEFAULT_DB_ALIAS, '--fake-initial', verbosity=1)
            except Exception as e:
                err_code = getattr(e, 'args', [None])[0] if getattr(e, 'args', None) else None
                err_str = str(e).lower()
                if err_code == 1050 or 'already exists' in err_str:
                    self.stdout.write(self.style.WARNING('Table(s) already exist; faking cheradip migrations and retrying...'))
                    call_command('migrate', 'cheradip', '--database=%s' % DEFAULT_DB_ALIAS, '--fake', verbosity=1)
                    try:
                        call_command('migrate', '--database=%s' % DEFAULT_DB_ALIAS, '--fake-initial', verbosity=1)
                    except Exception as e2:
                        self.stdout.write(self.style.ERROR('Migrate failed: %s' % e2))
                        return
                else:
                    self.stdout.write(self.style.ERROR('Migrate failed: %s' % e))
                    return
            self.stdout.write(self.style.SUCCESS('Migrations applied on default database.'))

        # Quick check for key tables
        with connection.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE'",
                [db_name],
            )
            existing = {row[0] for row in cur.fetchall()}
        needed = {'auth_group', 'auth_permission', 'cheradip_customers', 'django_content_type', 'django_session'}
        missing = needed - existing
        if missing:
            self.stdout.write(self.style.WARNING('Missing tables: %s' % ', '.join(sorted(missing))))
        else:
            self.stdout.write(self.style.SUCCESS('Default Django user panel tables are present on cheradip_cheradip.'))

        self.stdout.write('')
        self.stdout.write('Django admin (user panel): open /admin/ in your browser.')
        self.stdout.write('Users = Customers (cheradip_customers). Groups = auth_group. Both use database: %s' % db_name)
        self.stdout.write('')

        if options.get('createsuperuser') and not options['check_only']:
            self.stdout.write('Creating superuser (Customer)...')
            call_command('createsuperuser', verbosity=1)
