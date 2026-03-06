"""
Create job-related tables in cheradip_job database.
If each table exists in the default database (cheradip_cheradip), copies its structure to cheradip_job.
Otherwise creates the table in cheradip_job using Django model schema.

Tables (from models): merit5, merit6, merit7, vacancy5, vacancy6, vacancy7,
  recommend5, recommend6, recommend7, banbeis.

Prerequisites:
- Database cheradip_job must exist.
- Django DATABASES has key 'job' pointing to it.

Run:
  python manage.py create_job_tables
  python manage.py create_job_tables --dry-run
"""
import re
from django.core.management.base import BaseCommand
from django.db import connections

# Table names in DB (from model Meta.db_table)
JOB_TABLE_NAMES = [
    'cheradip_merit5',
    'cheradip_merit6',
    'cheradip_merit7',
    'cheradip_vacancy5',
    'cheradip_vacancy6',
    'cheradip_vacancy7',
    'cheradip_recommend5',
    'cheradip_recommend6',
    'cheradip_recommend7',
    'cheradip_banbeis',
]

def get_create_sql_from_default(conn_default, table_name):
    """Return CREATE TABLE statement from default DB, or None if table missing."""
    try:
        with conn_default.cursor() as cur:
            cur.execute("SHOW CREATE TABLE `%s`" % table_name.replace('`', '``'))
            row = cur.fetchone()
        if not row:
            return None
        return row[1]
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Create merit, vacancy, recommend, banbeis tables in cheradip_job (from default if exist, else from models)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        default_conn = connections['default']
        job_conn = connections['job']
        default_db = default_conn.settings_dict['NAME']

        # Map db_table -> model class for fallback create from schema (built on first need)
        table_to_model = None

        created = 0
        skipped = 0
        for table_name in JOB_TABLE_NAMES:
            create_sql = get_create_sql_from_default(default_conn, table_name)
            if create_sql:
                if dry_run:
                    self.stdout.write('Would create %s in job (from default DDL).' % table_name)
                    created += 1
                    continue
                try:
                    # Strip default DB name from CREATE so it runs in job (e.g. `cheradip_cheradip`.`tbl` -> `tbl`)
                    sql = create_sql
                    if default_db:
                        sql = re.sub(r'`%s`\.' % re.escape(default_db), '', sql)
                    match = re.search(r'CREATE TABLE (?:`[^`]+`\.)?`([^`]+)`', sql)
                    tname = match.group(1) if match else table_name
                    with job_conn.cursor() as cur:
                        cur.execute("DROP TABLE IF EXISTS `%s`" % tname.replace('`', '``'))
                        cur.execute(sql)
                    self.stdout.write('Created %s in cheradip_job.' % table_name)
                    created += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR('Failed %s: %s' % (table_name, e)))
            else:
                # Fallback: create from Django model schema
                if table_to_model is None:
                    from cheradip.models import Merit5, Merit6, Merit, Vacancy5, Vacancy6, Vacancy
                    from cheradip.models import Recommend5, Recommend6, Recommend, Banbeis
                    table_to_model = {
                        'cheradip_merit5': Merit5, 'cheradip_merit6': Merit6, 'cheradip_merit7': Merit,
                        'cheradip_vacancy5': Vacancy5, 'cheradip_vacancy6': Vacancy6, 'cheradip_vacancy7': Vacancy,
                        'cheradip_recommend5': Recommend5, 'cheradip_recommend6': Recommend6, 'cheradip_recommend7': Recommend,
                        'cheradip_banbeis': Banbeis,
                    }
                model_class = table_to_model.get(table_name)
                if model_class and not dry_run:
                    try:
                        with job_conn.cursor() as cur:
                            cur.execute("DROP TABLE IF EXISTS `%s`" % table_name.replace('`', '``'))
                        with job_conn.schema_editor() as schema_editor:
                            schema_editor.create_model(model_class)
                        self.stdout.write('Created %s in cheradip_job (from model).' % table_name)
                        created += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR('Failed %s (from model): %s' % (table_name, e)))
                elif model_class and dry_run:
                    self.stdout.write('Would create %s in job (from model schema).' % table_name)
                    created += 1
                else:
                    self.stdout.write('Skipped %s (not in default DB and no model mapping).' % table_name)
                    skipped += 1

        if not dry_run:
            self.stdout.write(self.style.SUCCESS('Done. Created %d table(s), skipped %d.' % (created, skipped)))
        else:
            self.stdout.write('Would create %d table(s), skip %d.' % (created, skipped))
