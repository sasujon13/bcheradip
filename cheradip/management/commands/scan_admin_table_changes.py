"""Observe even external/raw-SQL changes without installing blocking DB triggers."""
import hashlib
import json
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.models import Max
from cheradip.models import AdminTableFingerprint, AdminTableEvent


def table_digest(connection, table):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', table):
        raise CommandError('Unsafe table name.')
    digest = hashlib.sha256()
    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(cursor, table)
        pk = connection.introspection.get_primary_key_column(cursor, table)
        quote = lambda value: '`' + value.replace('`', '``') + '`'
        order = quote(pk) if pk else ', '.join(quote(column.name) for column in columns)
        cursor.execute(f'SELECT * FROM `{table}` ORDER BY {order}')
        while True:
            batch = cursor.fetchmany(500)
            if not batch:
                break
            for row in batch:
                digest.update(json.dumps(row, default=str, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
                digest.update(b'\n')
    return digest.hexdigest()


class Command(BaseCommand):
    help = 'Refresh change markers for all databases, including AILT/Agent and external/raw SQL. First run establishes a baseline. Read-only on source databases.'

    def add_arguments(self, parser):
        parser.add_argument('--database', action='append', choices=list(connections))
        parser.add_argument('--table', action='append')

    def handle(self, *args, **options):
        failed = []
        for alias in options['database'] or list(connections):
            connection = connections[alias]
            try:
                with connection.cursor() as cursor:
                    tables = connection.introspection.table_names(cursor)
                for table in tables:
                    if table.startswith(('cheradip_admin_table_', 'django_', 'auth_')):
                        continue
                    if options['table'] and table not in options['table']:
                        continue
                    if not re.fullmatch(r'[a-z][a-z0-9_]*', table):
                        continue
                    digest = table_digest(connection, table)
                    with transaction.atomic(using='default'):
                        checkpoint, created = AdminTableFingerprint.objects.select_for_update().get_or_create(
                            database_alias=alias, table_name=table, defaults={'digest': digest})
                        latest = AdminTableEvent.objects.filter(database_alias=alias, table_name=table).aggregate(last=Max('id'))['last'] or 0
                        if not created and checkpoint.digest != digest and latest == checkpoint.last_event_id:
                            event = AdminTableEvent.objects.create(database_alias=alias, table_name=table, action='external change')
                            latest = event.pk
                            self.stdout.write(f'{alias}.{table}: external change observed.')
                        checkpoint.digest, checkpoint.last_event_id = digest, latest
                        checkpoint.save(update_fields=['digest', 'last_event_id'])
            except Exception as exc:
                # A stopped independent service must not interrupt other databases.
                self.stderr.write(f'{alias}: scan incomplete ({type(exc).__name__}). Other databases continue.')
                failed.append(alias)
        if failed:
            raise CommandError('Scans incomplete for: ' + ', '.join(failed))
