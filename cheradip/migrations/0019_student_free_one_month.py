import calendar

from django.db import migrations


STUDENT_FREE_CODES = ('free-academic', 'free-admission', 'free-combined')


def add_month(value):
    month_index = value.month
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def set_student_free_to_one_month(apps, schema_editor):
    Plan = apps.get_model('cheradip', 'PackagePlan')
    Subscription = apps.get_model('cheradip', 'PackageSubscription')

    Plan.objects.filter(code__in=STUDENT_FREE_CODES).update(duration_months=1)
    for subscription in Subscription.objects.filter(
        plan__code__in=STUDENT_FREE_CODES,
        status__in=['active', 'grace'],
        starts_at__isnull=False,
    ):
        ends_at = add_month(subscription.starts_at)
        Subscription.objects.filter(pk=subscription.pk).update(
            ends_at=ends_at,
            next_renewal_at=ends_at,
            auto_renew=False,
        )


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0018_free_packages_36_months')]

    operations = [
        migrations.RunPython(set_student_free_to_one_month, migrations.RunPython.noop),
    ]
