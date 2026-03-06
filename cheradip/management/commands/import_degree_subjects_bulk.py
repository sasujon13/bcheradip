"""
Bulk import Degree / Honours / Masters subjects (class_level 13-16) from CSV or JSON.

CSV: first row may be header (subject_code, subject_name, subject_translated, country_id).
     Columns in any order; country_id optional (default from --country).
     subject_code max 12 chars.

JSON: array of objects with keys: subject_code, subject_name, subject_translated, country_id (optional).

Example:
  python manage.py import_degree_subjects_bulk --file degree_subjects.csv --format csv
  python manage.py import_degree_subjects_bulk --file degree_subjects.json --format json --country BD
"""
import csv
import json
from django.core.management.base import BaseCommand
from django.db import transaction

from cheradip.models import Subject


DEGREE_LEVEL = 'Degree / Honours / Masters'
CLASS_LEVEL = '13-16'


def _get_key(row, *keys):
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return (v or '').strip()
    return ''


def normalize_row(row, country_default='BD'):
    """Expect dict with subject_code, subject_name, subject_translated; optional country_id. Keys may be lowercase with underscores."""
    row = {str(k).strip().lower().replace(' ', '_'): v for k, v in (row or {}).items()}
    subject_code = (_get_key(row, 'subject_code', 'subjectcode') or '')[:12]
    subject_name = _get_key(row, 'subject_name', 'subjectname') or None
    subject_translated = _get_key(row, 'subject_translated', 'subjecttranslated') or None
    country_id = (_get_key(row, 'country_id', 'countryid') or country_default or 'BD')[:2] or 'BD'
    if not subject_code or not subject_translated:
        return None
    return {
        'subject_code': subject_code,
        'subject_name': subject_name,
        'subject_translated': subject_translated,
        'country_id': country_id,
    }


def load_rows_from_csv(path, encoding='utf-8-sig'):
    rows = []
    with open(path, 'r', encoding=encoding, newline='', errors='replace') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return rows
        for row in reader:
            rows.append(dict(row))
    return rows


def load_rows_from_json(path, encoding='utf-8'):
    with open(path, 'r', encoding=encoding, errors='replace') as f:
        return _parse_json_data(json.load(f))


def _parse_json_data(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and 'subjects' in data:
        return data['subjects']
    return []


def load_rows_from_csv_file(file_handle, encoding='utf-8'):
    import io
    content = file_handle.read() if hasattr(file_handle, 'read') else file_handle
    if isinstance(content, bytes):
        content = content.decode(encoding, errors='replace')
    reader = csv.DictReader(io.StringIO(content))
    return list(reader) if reader.fieldnames else []


def load_rows_from_json_file(file_handle, encoding='utf-8'):
    raw = file_handle.read() if hasattr(file_handle, 'read') else file_handle
    if isinstance(raw, bytes):
        raw = raw.decode(encoding, errors='replace')
    data = json.loads(raw)
    return _parse_json_data(data)


def import_degree_subjects(rows, country_default='BD', verbose=False):
    """Create or update Subject rows for Degree (13-16). Returns (created, updated, skipped)."""
    created = updated = skipped = 0
    for row in rows:
        parsed = normalize_row(row, country_default)
        if not parsed:
            skipped += 1
            continue
        subject_code = parsed['subject_code']
        if not subject_code:
            skipped += 1
            continue
        with transaction.atomic():
            sub, was_created = Subject.objects.update_or_create(
                subject_code=subject_code,
                defaults={
                    'level': DEGREE_LEVEL,
                    'level_tr': DEGREE_LEVEL,
                    'class_level': CLASS_LEVEL,
                    'subject_name': parsed['subject_name'],
                    'subject_translated': parsed['subject_translated'],
                    'country_id': parsed['country_id'],
                    'groups': None,
                }
            )
            if was_created:
                created += 1
                if verbose:
                    print(f'Created: {subject_code}')
            else:
                updated += 1
                if verbose:
                    print(f'Updated: {subject_code}')
    return created, updated, skipped


class Command(BaseCommand):
    help = 'Bulk import Degree / Honours / Masters subjects from CSV or JSON'

    def add_arguments(self, parser):
        parser.add_argument('--file', '-f', required=True, help='Path to CSV or JSON file')
        parser.add_argument('--format', '-t', choices=['csv', 'json'], default=None,
                            help='File format (auto-detect from extension if omitted)')
        parser.add_argument('--country', '-c', default='BD', help='Default country_id for rows without one')
        parser.add_argument('--encoding', default='utf-8-sig', help='File encoding')

    def handle(self, *args, **options):
        path = options['file']
        fmt = options['format']
        if not fmt:
            if path.lower().endswith('.json'):
                fmt = 'json'
            else:
                fmt = 'csv'
        country = (options['country'] or 'BD').strip()[:2] or 'BD'
        try:
            if fmt == 'csv':
                rows = load_rows_from_csv(path, options['encoding'])
            else:
                rows = load_rows_from_json(path, options['encoding'])
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'File not found: {path}'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return
        if not rows:
            self.stdout.write('No rows to import.')
            return
        created, updated, skipped = import_degree_subjects(rows, country_default=country, verbose=options['verbosity'] > 1)
        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} created, {updated} updated, {skipped} skipped.'
        ))
