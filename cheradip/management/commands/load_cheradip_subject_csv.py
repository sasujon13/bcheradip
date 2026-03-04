"""
Load cheradip_subject from CSV: cheradip_database - all.csv
Columns: id, level, level_tr, groups, class, subject_name, subject_translated, subject_code, country_id, language_code, created_at, updated_at
"""
import csv
from django.core.management.base import BaseCommand
from cheradip.models import Subject


class Command(BaseCommand):
    help = 'Load cheradip_subject from CSV (e.g. cheradip_database - all.csv)'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_path',
            nargs='?',
            default=r'C:\Users\sasha\Desktop\database\cheradip_database - all.csv',
            help='Path to CSV file',
        )
        parser.add_argument('--truncate', action='store_true', help='Truncate cheradip_subject before load')

    def handle(self, *args, **options):
        path = options['csv_path']
        truncate = options['truncate']
        try:
            with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'File not found: {path}'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return
        if not rows:
            self.stdout.write('CSV is empty.')
            return
        if truncate:
            n = Subject.objects.count()
            Subject.objects.all().delete()
            self.stdout.write(f'Truncated {n} rows.')
        created = 0
        for row in rows:
            try:
                groups = row.get('groups') or None
                if groups and isinstance(groups, str) and groups.strip():
                    import json
                    try:
                        groups = json.loads(groups)
                    except json.JSONDecodeError:
                        groups = [g.strip() for g in groups.split(',') if g.strip()]
                else:
                    groups = None
                class_val = row.get('class', '').strip()
                if class_val.isdigit():
                    class_level = class_val
                elif class_val in ('9-10', '9–10'):
                    class_level = '9-10'
                elif class_val in ('11-12', '11–12'):
                    class_level = '11-12'
                elif class_val in ('13-16', '13–16'):
                    class_level = '13-16'
                else:
                    class_level = None
                Subject.objects.create(
                    level=(row.get('level') or '').strip() or None,
                    level_tr=(row.get('level_tr') or '').strip() or None,
                    groups=groups,
                    class_level=class_level,
                    subject_name=(row.get('subject_name') or '').strip() or None,
                    subject_translated=(row.get('subject_translated') or '').strip() or None,
                    subject_code=(row.get('subject_code') or '').strip() or '',
                    country_id=(row.get('country_id') or '').strip() or None,
                    language_code=(row.get('language_code') or '').strip() or None,
                )
                created += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Skip row: {e}'))
                continue
        self.stdout.write(self.style.SUCCESS(f'Loaded {created} rows into cheradip_subject.'))
