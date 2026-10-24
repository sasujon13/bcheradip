"""Add only the new store-pricing JSON column on pre-existing deployments."""
from django.core.management.base import BaseCommand,CommandError
from django.db import connections
from ecommerce.models import DeliverySettings

class Command(BaseCommand):
    help='Check or add only DeliverySettings.pricing_rules. Does not migrate/restore unrelated tables or rows.'
    def add_arguments(self,parser):parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        connection=connections['ecommerce'];table=DeliverySettings._meta.db_table
        with connection.cursor() as cursor:
            if table not in connection.introspection.table_names(cursor):raise CommandError('Existing store settings table is missing; run normal project schema setup first.')
            columns={c.name for c in connection.introspection.get_table_description(cursor,table)}
        if 'pricing_rules' in columns:self.stdout.write('Store pricing column already exists; no data overwritten.');return
        if not options['apply']:raise CommandError('Store pricing column missing. Run with --apply for this single additive column.')
        with connection.schema_editor() as editor:editor.add_field(DeliverySettings,DeliverySettings._meta.get_field('pricing_rules'))
        self.stdout.write('Added only the store pricing JSON column with approved default bands; existing records preserved.')
