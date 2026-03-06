"""
Create cheradip_subject in the honours database (same structure as default)
and copy all rows from default DB cheradip_subject into it.

Prerequisites:
- Database cheradip_honours must already exist.
- Django DATABASES has a key 'honours' pointing to it.

Run:
  python manage.py copy_subject_to_honours_db
  python manage.py copy_subject_to_honours_db --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connections

CREATE_CHERADIP_SUBJECT = """
CREATE TABLE IF NOT EXISTS cheradip_subject (
    id INT AUTO_INCREMENT PRIMARY KEY,
    level VARCHAR(100) NULL,
    level_tr VARCHAR(100) NULL,
    groups JSON NULL,
    class_level VARCHAR(10) NULL,
    subject_name VARCHAR(255) NULL,
    subject_translated VARCHAR(255) NULL,
    subject_code VARCHAR(12) NOT NULL,
    country_id VARCHAR(2) NULL,
    language_code VARCHAR(10) NULL,
    created_at DATETIME(6) NULL,
    updated_at DATETIME(6) NULL,
    UNIQUE KEY (subject_code),
    INDEX (subject_code),
    INDEX (country_id),
    INDEX (country_id, level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class Command(BaseCommand):
    help = 'Create cheradip_subject in honours DB and copy all rows from default cheradip_subject'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be done.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        default_conn = connections['default']
        honours_conn = connections['honours']

        if not dry_run:
            with honours_conn.cursor() as cur:
                cur.execute(CREATE_CHERADIP_SUBJECT)
            self.stdout.write('Created table cheradip_subject in honours database.')
        else:
            self.stdout.write('Would create table cheradip_subject in honours database.')

        with default_conn.cursor() as cur:
            cur.execute("""
                SELECT level, level_tr, groups, class_level, subject_name, subject_translated,
                       subject_code, country_id, language_code, created_at, updated_at
                FROM cheradip_subject
                ORDER BY id
            """)
            rows = cur.fetchall()

        if not rows:
            self.stdout.write('No rows in default cheradip_subject.')
            return

        self.stdout.write('Found %d rows in default cheradip_subject.' % len(rows))

        if dry_run:
            self.stdout.write('Would copy %d rows to honours.cheradip_subject.' % len(rows))
            return

        copied = 0
        for r in rows:
            with honours_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cheradip_subject
                    (level, level_tr, groups, class_level, subject_name, subject_translated,
                     subject_code, country_id, language_code, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, r)
            copied += 1

        self.stdout.write(self.style.SUCCESS('Copied %d rows to honours.cheradip_subject.' % copied))
