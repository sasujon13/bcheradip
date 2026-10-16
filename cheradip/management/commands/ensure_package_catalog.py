"""Install the versioned package catalog without copying customer data.

The remote table-sync command creates missing tables but deliberately never
copies rows. Historical data migrations may not run on a server whose migration
history predates its schema, so deployment must install missing catalog plans
explicitly. Existing plans are checked, never silently overwritten.
"""

from decimal import Decimal
from importlib import import_module

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cheradip.models import PackagePlan


def expected_plans():
    original = import_module('cheradip.migrations.0011_seed_package_plans')
    limits = import_module('cheradip.migrations.0015_package_plan_audience').QUESTION_LIMITS
    for order, (slug, name, months, list_prices, prices) in enumerate(original.PLAN_ROWS):
        for track_index, track in enumerate(original.TRACKS):
            for audience in ('student', 'teacher'):
                code = f'{slug}-{track}' if audience == 'student' else f'teacher-{slug}-{track}'
                yield code, {
                    'name': name,
                    'duration_months': (1 if audience == 'student' else 36) if slug == 'free' else months,
                    'track': track,
                    'audience': audience,
                    'list_price': Decimal(list_prices[track_index]),
                    'price': Decimal(prices[track_index]),
                    'question_limit': limits[slug] * (2 if track == 'combined' else 1) if audience == 'teacher' else 0,
                    'currency': 'BDT',
                    'is_active': True,
                    'sort_order': order,
                    'features': [],
                }


class Command(BaseCommand):
    help = 'Check package plans; optionally add missing canonical plans without changing existing rows.'

    def add_arguments(self, parser):
        parser.add_argument('--apply-missing', action='store_true',
                            help='Insert missing plans only; fail on differing existing plans.')

    def handle(self, *args, **options):
        expected = dict(expected_plans())
        created = []
        mismatches = []
        with transaction.atomic():
            existing = PackagePlan.objects.in_bulk(expected.keys(), field_name='code')
            for code, values in expected.items():
                plan = existing.get(code)
                if plan is None:
                    if options['apply_missing']:
                        PackagePlan.objects.create(code=code, **values)
                        created.append(code)
                    else:
                        mismatches.append(f'{code}: missing')
                    continue
                differing = [field for field, value in values.items() if getattr(plan, field) != value]
                if differing:
                    mismatches.append(f'{code}: differs in {", ".join(differing)}')
            if mismatches:
                for message in mismatches:
                    self.stderr.write(message)
                raise CommandError(f'Package catalog is incomplete or differs in {len(mismatches)} plan(s).')
        self.stdout.write(self.style.SUCCESS(
            f'Package catalog verified: {len(expected)} plans; {len(created)} missing plan(s) added.'
        ))
