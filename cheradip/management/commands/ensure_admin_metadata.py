"""Install permission definitions without granting access or copying business data."""
from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create missing admin content types and permission definitions; never assign permissions to accounts/groups.'

    def add_arguments(self, parser):
        parser.add_argument('--apply-missing', action='store_true')

    def handle(self, *args, **options):
        if not options['apply_missing']:
            self.stdout.write('Read-only: pass --apply-missing to install missing permission definitions (no user/group grants).')
            return
        before = (ContentType.objects.using('default').count(), Permission.objects.using('default').count())
        for label in ('auth', 'cheradip', 'ecommerce'):
            create_permissions(apps.get_app_config(label), using='default', verbosity=0, interactive=False)
        after = (ContentType.objects.using('default').count(), Permission.objects.using('default').count())
        self.stdout.write(self.style.SUCCESS(
            f'Admin metadata ready: {after[0] - before[0]} content types and {after[1] - before[1]} permission definitions added. No account/group grants changed.'))
