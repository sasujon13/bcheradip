from django.db import migrations
from django.utils import timezone


def supersede_free_packages_with_paid_access(apps, schema_editor):
    Subscription = apps.get_model('cheradip', 'PackageSubscription')
    now = timezone.now()
    paid_pairs = Subscription.objects.filter(
        status__in=['active', 'grace'],
    ).exclude(plan__name='Free').values_list(
        'customer_id', 'plan__audience',
    ).distinct()

    for customer_id, audience in paid_pairs.iterator():
        Subscription.objects.filter(
            customer_id=customer_id,
            plan__audience=audience,
            plan__name='Free',
            status__in=['active', 'grace'],
        ).update(
            status='superseded',
            auto_renew=False,
            superseded_at=now,
        )


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0019_student_free_one_month')]

    operations = [
        migrations.RunPython(supersede_free_packages_with_paid_access, migrations.RunPython.noop),
    ]
