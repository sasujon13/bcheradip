from django.db import migrations


PLAN_ROWS = [
    ('free', 'Free', 1, (150, 150, 225), (0, 0, 0)),
    ('starter', 'Starter', 1, (150, 150, 300), (150, 150, 225)),
    ('basic', 'Basic', 3, (450, 450, 900), (360, 360, 540)),
    ('intermediate', 'Int.', 6, (900, 900, 1800), (630, 630, 945)),
    ('advanced-0', 'Adv. 0', 12, (1800, 1800, 3600), (1080, 1080, 1620)),
    ('advanced-1', 'Adv. 1', 18, (2700, 2700, 5400), (1440, 1440, 2160)),
    ('advanced-2', 'Adv. 2', 24, (3600, 3600, 7200), (1680, 1680, 2520)),
    ('advanced-3', 'Adv. 3', 36, (5400, 5400, 10800), (2160, 2160, 3240)),
]
TRACKS = ('academic', 'admission', 'combined')


def seed_plans(apps, schema_editor):
    Plan = apps.get_model('cheradip', 'PackagePlan')
    for order, (slug, name, months, list_prices, prices) in enumerate(PLAN_ROWS):
        for index, track in enumerate(TRACKS):
            Plan.objects.update_or_create(
                code=f'{slug}-{track}',
                defaults={
                    'name': name,
                    'duration_months': months,
                    'track': track,
                    'list_price': list_prices[index],
                    'price': prices[index],
                    'currency': 'BDT',
                    'is_active': True,
                    'sort_order': order,
                    'features': [],
                },
            )


def remove_seeded_plans(apps, schema_editor):
    Plan = apps.get_model('cheradip', 'PackagePlan')
    codes = [f'{slug}-{track}' for slug, *_rest in PLAN_ROWS for track in TRACKS]
    Plan.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0010_membershipprogress_packageplan_packagesubscription')]
    operations = [migrations.RunPython(seed_plans, remove_seeded_plans)]
