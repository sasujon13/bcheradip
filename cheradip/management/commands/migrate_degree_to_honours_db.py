"""
Create cheradip_subject in the honours database (same structure as default),
copy unique degree/honours subjects (by subject_name) into honours as Honours / 13-16,
then remove degree/honours subjects from default cheradip_subject.

Prerequisites:
- Database cheradip_honours must already exist.
- Django DATABASES has a key 'honours' pointing to it.

Run:
  python manage.py migrate_degree_to_honours_db
  python manage.py migrate_degree_to_honours_db --dry-run  # show what would be done
"""
import re
from django.core.management.base import BaseCommand
from django.db import connections

# Same structure as cheradip_subject in default DB (Subject model)
CREATE_CHERADIP_SUBJECT_HONOURS = """
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

DEGREE_LEVEL = 'Degree / Honours / Masters'
CLASS_LEVEL_13_16 = '13-16'
HONOURS_LEVEL = 'Honours'


def _slug_for_code(name, max_chars=6):
    """Short slug for subject_code: alphanumeric/underscore, max max_chars."""
    if not name or not isinstance(name, str):
        return 'SUB'
    s = re.sub(r'[^a-zA-Z0-9]', '_', name.strip().upper())[:max_chars]
    return s or 'SUB'


def _generate_honours_subject_code(subject_translated, country_id, existing_codes):
    """Generate unique subject_code for honours (max 12 chars)."""
    cid = (country_id or 'BD')[:2]
    base = _slug_for_code(subject_translated, 6)
    if f'HON_{base}_{cid}' not in existing_codes and len(f'HON_{base}_{cid}') <= 12:
        code = f'HON_{base}_{cid}'
        existing_codes.add(code)
        return code
    for suffix in range(1, 1000):
        code = f'HON_{base[:4]}_{cid}{suffix}'[:12]
        if code not in existing_codes:
            existing_codes.add(code)
            return code
    import hashlib
    h = hashlib.md5((str(subject_translated) + str(country_id)).encode()).hexdigest()[:4].upper()
    code = f'HON_{h}_{cid}'[:12]
    existing_codes.add(code)
    return code


class Command(BaseCommand):
    help = 'Create cheradip_subject in honours DB, migrate degree subjects as Honours, remove from default'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only show what would be done; do not create table, insert, or delete.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN – no changes will be made.'))

        default_conn = connections['default']
        honours_conn = connections['honours']

        # 1) Create table in honours DB
        if dry_run:
            self.stdout.write('Would create table cheradip_subject in honours database.')
        else:
            with honours_conn.cursor() as cur:
                cur.execute(CREATE_CHERADIP_SUBJECT_HONOURS)
            self.stdout.write('Created table cheradip_subject in honours database.')

        # 2) Fetch degree/honours subjects from default (level = Degree / Honours / Masters, class_level = 13-16)
        with default_conn.cursor() as cur:
            cur.execute("""
                SELECT id, level, level_tr, groups, class_level, subject_name, subject_translated,
                       subject_code, country_id, language_code, created_at, updated_at
                FROM cheradip_subject
                WHERE level = %s AND class_level = %s
                ORDER BY country_id, subject_name, id
            """, [DEGREE_LEVEL, CLASS_LEVEL_13_16])
            rows = cur.fetchall()

        if not rows:
            self.stdout.write('No degree/honours subjects (level=%s, class_level=%s) found in default DB.' % (DEGREE_LEVEL, CLASS_LEVEL_13_16))
            return

        # Unique by (subject_name, country_id) – keep first subject_translated
        seen = set()
        unique_rows = []
        for r in rows:
            subject_name = (r[5] or '').strip()
            country_id = (r[8] or 'BD')[:2]
            key = (subject_name, country_id)
            if not subject_name or key in seen:
                continue
            seen.add(key)
            unique_rows.append(r)

        self.stdout.write('Found %d degree/honours rows; %d unique by (subject_name, country_id).' % (len(rows), len(unique_rows)))

        # 3) Insert into honours DB with level='Honours', class_level='13-16'
        existing_codes = set()
        if not dry_run:
            with honours_conn.cursor() as cur:
                cur.execute("SELECT subject_code FROM cheradip_subject")
                existing_codes.update(row[0] for row in cur.fetchall())

        inserted = 0
        for r in unique_rows:
            (_id, level, level_tr, groups, class_level, subject_name, subject_translated,
             subject_code_old, country_id, language_code, created_at, updated_at) = r
            country_id = (country_id or 'BD')[:2]
            subject_code = _generate_honours_subject_code(subject_translated or subject_name, country_id, existing_codes)
            if dry_run:
                self.stdout.write('  Would insert: %s -> %s (Honours, 13-16)' % (subject_translated or subject_name, subject_code))
                inserted += 1
                continue
            with honours_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cheradip_subject
                    (level, level_tr, groups, class_level, subject_name, subject_translated, subject_code,
                     country_id, language_code, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, [
                    HONOURS_LEVEL, HONOURS_LEVEL, groups, CLASS_LEVEL_13_16,
                    subject_name, subject_translated, subject_code,
                    country_id, language_code, created_at, updated_at,
                ])
            inserted += 1

        self.stdout.write('Inserted %d rows into honours.cheradip_subject.' % inserted)

        # 4) Delete degree/honours subjects from default DB
        with default_conn.cursor() as cur:
            if dry_run:
                self.stdout.write('Would delete %d rows from default cheradip_subject (degree/honours).' % len(rows))
            else:
                cur.execute(
                    "DELETE FROM cheradip_subject WHERE level = %s AND class_level = %s",
                    [DEGREE_LEVEL, CLASS_LEVEL_13_16]
                )
                self.stdout.write(self.style.SUCCESS('Deleted %d degree/honours rows from default cheradip_subject.' % len(rows)))
