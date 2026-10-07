from django.db import migrations, models


QUESTION_LIMITS = {
    'free': 15,
    'starter': 20,
    'basic': 45,
    'intermediate': 90,
    'advanced-0': 180,
    'advanced-1': 270,
    'advanced-2': 360,
    'advanced-3': 540,
}


def populate_question_limits(apps, schema_editor):
    Plan = apps.get_model('cheradip', 'PackagePlan')
    Subscription = apps.get_model('cheradip', 'PackageSubscription')
    for slug, limit in QUESTION_LIMITS.items():
        for track in ('academic', 'admission', 'combined'):
            value = limit * 2 if track == 'combined' else limit
            Plan.objects.filter(code=f'{slug}-{track}').update(question_limit=value)
    for row in Subscription.objects.select_related('plan').all().iterator():
        Subscription.objects.filter(pk=row.pk).update(question_limit_snapshot=row.plan.question_limit)


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0013_referrals_and_membership_maintenance')]

    operations = [
        migrations.AddField(
            model_name='packageplan',
            name='question_limit',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='packagesubscription',
            name='question_limit_snapshot',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='packagesubscription',
            name='questions_used',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(populate_question_limits, migrations.RunPython.noop),
    ]
