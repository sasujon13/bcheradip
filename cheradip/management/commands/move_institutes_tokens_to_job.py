"""
Move cheradip_institutes and cheradip_tokens from cheradip_cheradip (default)
to cheradip_job: create tables in job, copy all rows, then drop tables from default.

Prerequisites:
- Database cheradip_job must exist.
- Django DATABASES has key 'job' pointing to it.

Run:
  python manage.py move_institutes_tokens_to_job
  python manage.py move_institutes_tokens_to_job --dry-run
"""
import re
from django.core.management.base import BaseCommand
from django.db import connections

TABLES = ['cheradip_institutes', 'cheradip_tokens']


def get_create_sql(conn, table_name):
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW CREATE TABLE `%s`" % table_name.replace('`', '``'))
            row = cur.fetchone()
        return row[1] if row else None
    except Exception:
        return None


class Command(BaseCommand):
    help = 'Move cheradip_institutes and cheradip_tokens from default DB to cheradip_job'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        default_conn = connections['default']
        job_conn = connections['job']
        default_db = default_conn.settings_dict['NAME']
        job_db = job_conn.settings_dict['NAME']

        for table_name in TABLES:
            create_sql = get_create_sql(default_conn, table_name)
            if not create_sql:
                self.stdout.write(self.style.ERROR('Table %s not found in default DB.' % table_name))
                continue

            if dry_run:
                with default_conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM `%s`" % table_name.replace('`', '``'))
                    n = cur.fetchone()[0]
                self.stdout.write('Would move %s (%d rows) to %s.' % (table_name, n, job_db))
                continue

            # 1) Create table in job (strip default DB name from DDL)
            sql = re.sub(r'`%s`\.' % re.escape(default_db), '', create_sql) if default_db else create_sql
            match = re.search(r'CREATE TABLE (?:`[^`]+`\.)?`([^`]+)`', sql)
            tname = match.group(1) if match else table_name
            with job_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS `%s`" % tname.replace('`', '``'))
                cur.execute(sql)
            self.stdout.write('Created %s in %s.' % (table_name, job_db))

            # 2) Copy data: INSERT INTO job.table SELECT * FROM default.table
            with default_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO `%s`.`%s` SELECT * FROM `%s`.`%s`"
                    % (job_db, table_name.replace('`', '``'), default_db, table_name.replace('`', '``'))
                )
                copied = cur.rowcount
            self.stdout.write('Copied %d rows to %s.%s.' % (copied, job_db, table_name))

            # 3) Drop table from default
            with default_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS `%s`" % table_name.replace('`', '``'))
            self.stdout.write(self.style.SUCCESS('Dropped %s from default DB.' % table_name))

        if not dry_run:
            self.stdout.write(self.style.SUCCESS('Done. Moved %s to %s.' % (', '.join(TABLES), job_db)))
