"""Merge one completed remote institute crawl into local institute tables only.

Unlike mysql_db_sync --r2l, this never drops tables or touches accounts,
orders, questions, or other local data. It is safe to rerun after interruption.
"""

import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from .mysql_db_sync import (
    DEFAULT_SYNC_LOCAL_HOST, DEFAULT_SYNC_LOCAL_PORT,
    DEFAULT_SYNC_LOCAL_USER, DEFAULT_SYNC_LOCAL_PASSWORD,
    DEFAULT_SYNC_REMOTE_HOST, DEFAULT_SYNC_REMOTE_PORT,
    DEFAULT_SYNC_REMOTE_USER, DEFAULT_SYNC_REMOTE_PASSWORD,
    _open_sync_connection, _ssh_mysql_tunnel, env, load_dotenv,
)


# Database, table, EIIN column, natural unique key, columns owned by that table.
TABLES = (
    ('job', 'cheradip_institutes', 'eiinNo', ('eiinNo',), ()),
    ('job', 'cheradip_banbeis', 'EIIN', ('EIIN',), ('id',)),
    ('default', 'cheradip_institutesourcesnapshot', 'eiin', ('eiin',), ()),
    ('default', 'cheradip_instituteteacher', 'eiin', ('eiin', 'source_row_id'), ('id',)),
)
BATCH_SIZE = 200


def _unique_keys(cursor, table):
    cursor.execute(f'SHOW INDEX FROM `{table}`')
    indexes = {}
    for row in cursor.fetchall():
        if row[1] == 0 and row[4]:
            indexes.setdefault(row[2], []).append((row[3], row[4]))
    return {tuple(name for _, name in sorted(columns)) for columns in indexes.values()}


def _columns(cursor, table):
    cursor.execute(f'SHOW FULL COLUMNS FROM `{table}`')
    return {row[0]: row[1] for row in cursor.fetchall()}


def _check_table(source, destination, table, natural_key, skip):
    with source.cursor() as reader, destination.cursor() as writer:
        source_columns = _columns(reader, table)
        local_columns = _columns(writer, table)
        names = [name for name in source_columns if name not in skip]
        missing = set(names) - set(local_columns)
        if missing:
            raise CommandError(f'{table}: local table lacks source columns: {sorted(missing)}')
        def comparable_type(value):
            # MariaDB releases display integer widths differently.
            return re.sub(r'\b(tinyint|smallint|mediumint|int|bigint)\(\d+\)',
                          r'\1', value.lower())

        if any(comparable_type(source_columns[name]) != comparable_type(local_columns[name])
               for name in names):
            different = [name for name in names
                         if comparable_type(source_columns[name]) != comparable_type(local_columns[name])]
            raise CommandError(f'{table}: different local/remote column types: {different}')
        if natural_key not in _unique_keys(reader, table) or natural_key not in _unique_keys(writer, table):
            raise CommandError(f'{table}: expected natural unique key {natural_key} is absent.')
    return names


def _merge_table(source, destination, table, eiin_column, natural_key, names, eiins):
    with destination.cursor() as cursor:
        cursor.execute(f'SHOW FULL COLUMNS FROM `{table}`')
        temporal_columns = {
            names.index(row[0]): (row[0], row[3] == 'YES')
            for row in cursor.fetchall()
            if row[0] in names and re.match(r'^(date|datetime|timestamp)\b', row[1], re.I)
        }
    quoted = ', '.join(f'`{name}`' for name in names)
    placeholders = ', '.join(['%s'] * len(names))
    update_names = [name for name in names if name not in natural_key]
    nullable_temporal = {names[index] for index, (_name, nullable) in temporal_columns.items() if nullable}
    update_sql = ', '.join(
        f'`{name}`=COALESCE(VALUES(`{name}`), `{name}`)' if name in nullable_temporal
        else f'`{name}`=VALUES(`{name}`)'
        for name in update_names
    )
    upsert = f'INSERT INTO `{table}` ({quoted}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_sql}'
    total = 0
    invalid_dates = 0
    for offset in range(0, len(eiins), BATCH_SIZE):
        batch = eiins[offset:offset + BATCH_SIZE]
        match = ', '.join(['%s'] * len(batch))
        with source.cursor() as reader:
            reader.execute(
                f'SELECT {quoted} FROM `{table}` WHERE `{eiin_column}` IN ({match})', batch,
            )
            rows = reader.fetchall()
        if rows:
            cleaned = []
            for row in rows:
                values = list(row)
                for index, (name, nullable) in temporal_columns.items():
                    value = values[index]
                    if not isinstance(value, str):
                        continue
                    try:
                        date.fromisoformat(value[:10])
                    except ValueError:
                        if not nullable:
                            raise CommandError(f'{table}.{name}: invalid non-nullable remote date {value!r}')
                        values[index] = None
                        invalid_dates += 1
                cleaned.append(tuple(values))
            try:
                with destination.cursor() as writer:
                    writer.executemany(upsert, cleaned)
                destination.commit()
            except Exception:
                destination.rollback()
                raise
            total += len(rows)
        if (offset // BATCH_SIZE + 1) % 25 == 0:
            print(f'  {table}: {min(offset + BATCH_SIZE, len(eiins)):,}/{len(eiins):,} EIINs checked')
    if invalid_dates:
        print(f'  {table}: {invalid_dates:,} invalid remote dates ignored; existing local dates retained.')
    return total


class Command(BaseCommand):
    help = 'When the chosen remote institute run finishes, upsert only its successful institute data locally.'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True, help='The remote full-run UUID to import.')
        parser.add_argument('--force', action='store_true', help='Repeat a previously completed import.')
        parser.add_argument('--dry-run', action='store_true', help='Check readiness and schema without writing.')

    def handle(self, *args, **options):
        try:
            run_id = uuid.UUID(options['run_id']).hex
        except ValueError as exc:
            raise CommandError('Invalid run UUID.') from exc
        marker = Path(settings.BASE_DIR) / 'work' / 'institute_updates' / f'remote-sync-{run_id}.json'
        if marker.exists() and not options['force']:
            self.stdout.write(f'Already imported this run: {marker}')
            return

        load_dotenv([Path(settings.BASE_DIR) / 'scripts', Path(settings.BASE_DIR)])
        remote_host = env('REMOTE_HOST', DEFAULT_SYNC_REMOTE_HOST)
        remote_port = env('REMOTE_PORT', DEFAULT_SYNC_REMOTE_PORT)
        remote_user = env('REMOTE_USER', DEFAULT_SYNC_REMOTE_USER)
        remote_password = env('REMOTE_PASSWORD', DEFAULT_SYNC_REMOTE_PASSWORD)
        local_host = env('LOCAL_HOST', DEFAULT_SYNC_LOCAL_HOST)
        local_port = env('LOCAL_PORT', DEFAULT_SYNC_LOCAL_PORT)
        local_user = env('LOCAL_USER', DEFAULT_SYNC_LOCAL_USER)
        local_password = env('LOCAL_PASSWORD', DEFAULT_SYNC_LOCAL_PASSWORD)
        if not remote_host or not remote_user or remote_password is None:
            raise CommandError('Remote database connection is not configured.')
        if local_host not in {'127.0.0.1', 'localhost', '::1'}:
            raise CommandError('Refusing to import into a non-local database host.')

        with _ssh_mysql_tunnel(remote_host, remote_port) as (host, port):
            remote_default = _open_sync_connection(
                host, port, remote_user, remote_password, 'cheradip_cheradip')
            try:
                with remote_default.cursor() as cursor:
                    cursor.execute('SELECT status, total, retry_round, completed_at FROM '
                                   'cheradip_instituteupdaterun WHERE id=%s', (run_id,))
                    run = cursor.fetchone()
                    if not run:
                        raise CommandError('The specified remote institute run was not found.')
                    cursor.execute('SELECT eiin, detail FROM cheradip_instituteupdateattempt '
                                   'WHERE run_id=%s AND status=%s ORDER BY eiin',
                                   (run_id, 'completed'))
                    attempts = cursor.fetchall()
                self.stdout.write(
                    f'Remote run: {run[0]}; {len(attempts):,}/{run[1]:,} successful; '
                    f'retry round {run[2]}/3.')
                if run[0] != 'complete' or run[2] < 3:
                    self.stdout.write('Remote crawl or retries are still running; local data was not changed.')
                    return
                if not attempts:
                    raise CommandError('Completed run has no successful EIINs; refusing an empty sync.')
                if options['dry_run']:
                    self.stdout.write('Dry run: remote crawl is ready; local data was not changed.')
                    return

                all_eiins = [str(eiin) for eiin, _detail in attempts]
                emis_eiins = [str(eiin) for eiin, detail in attempts if not detail]
                counts = {}
                for alias, database in (('job', 'cheradip_job'),
                                        ('default', 'cheradip_cheradip')):
                    source = _open_sync_connection(host, port, remote_user, remote_password, database)
                    destination = _open_sync_connection(
                        local_host, local_port, local_user, local_password, database)
                    try:
                        with destination.cursor() as cursor:
                            cursor.execute("SET SESSION sql_mode=CONCAT_WS(',', @@sql_mode, 'STRICT_ALL_TABLES', 'NO_AUTO_VALUE_ON_ZERO')")
                        for table_alias, table, eiin_column, natural_key, skip in TABLES:
                            if table_alias != alias:
                                continue
                            names = _check_table(source, destination, table, natural_key, skip)
                            selected = emis_eiins if table == 'cheradip_instituteteacher' else all_eiins
                            counts[table] = _merge_table(source, destination, table, eiin_column,
                                                          natural_key, names, selected)
                            self.stdout.write(f'{table}: {counts[table]:,} remote rows merged locally.')
                    finally:
                        destination.close()
                        source.close()

                marker.parent.mkdir(parents=True, exist_ok=True)
                temporary = marker.with_suffix('.tmp')
                temporary.write_text(json.dumps({
                    'runId': str(uuid.UUID(run_id)),
                    'completedAt': run[3].isoformat() if run[3] else None,
                    'syncedAt': datetime.now(timezone.utc).isoformat(),
                    'successfulEiins': len(all_eiins),
                    'tables': counts,
                }, indent=2) + '\n', encoding='utf-8')
                temporary.replace(marker)
                self.stdout.write(self.style.SUCCESS(f'Institute-only local sync complete: {marker}'))
            finally:
                remote_default.close()
