"""Mirror the published plan matrix in disposable tests without running MySQL DDL."""
from importlib import import_module
from cheradip.models import PackagePlan


def seed_test_plans():
    source = import_module('cheradip.migrations.0011_seed_package_plans')
    limits = import_module('cheradip.migrations.0015_package_plan_audience').QUESTION_LIMITS
    for order, (slug, name, months, list_prices, prices) in enumerate(source.PLAN_ROWS):
        for index, track in enumerate(source.TRACKS):
            for audience in ('student', 'teacher'):
                code = f'{slug}-{track}' if audience == 'student' else f'teacher-{slug}-{track}'
                PackagePlan.objects.update_or_create(code=code, defaults={
                    'name': name, 'duration_months': (1 if audience == 'student' else 36) if name == 'Free' else months,
                    'audience': audience, 'track': track, 'list_price': list_prices[index], 'price': prices[index],
                    'question_limit': (limits[slug] * (2 if track == 'combined' else 1)) if audience == 'teacher' else 0,
                    'currency': 'BDT', 'is_active': True, 'sort_order': order, 'features': [],
                })
