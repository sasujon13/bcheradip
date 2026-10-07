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


def create_teacher_plans(apps, schema_editor):
    Plan = apps.get_model('cheradip', 'PackagePlan')
    for source in list(Plan.objects.filter(audience='student').order_by('sort_order', 'track')):
        slug = source.code.rsplit('-', 1)[0]
        limit = QUESTION_LIMITS.get(slug, 0)
        Plan.objects.update_or_create(
            code=f'teacher-{source.code}',
            defaults={
                'name': source.name,
                'duration_months': source.duration_months,
                'track': source.track,
                'audience': 'teacher',
                'list_price': source.list_price,
                'price': source.price,
                'question_limit': limit * 2 if source.track == 'combined' else limit,
                'currency': source.currency,
                'is_active': source.is_active,
                'sort_order': source.sort_order,
                'features': source.features,
            },
        )
    # Existing subscriptions were purchased from the original Student table.
    Plan.objects.filter(audience='student').update(question_limit=0)


def remove_teacher_plans(apps, schema_editor):
    Plan = apps.get_model('cheradip', 'PackagePlan')
    Plan.objects.filter(audience='teacher', code__startswith='teacher-').delete()


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0014_teacher_package_question_limits')]

    operations = [
        migrations.AddField(
            model_name='packageplan',
            name='audience',
            field=models.CharField(
                choices=[('student', 'Student'), ('teacher', 'Teacher')],
                db_index=True,
                default='student',
                max_length=12,
            ),
        ),
        migrations.AddIndex(
            model_name='packageplan',
            index=models.Index(fields=['audience', 'is_active', 'sort_order'], name='cheradip_pa_audienc_b722d4_idx'),
        ),
        migrations.RunPython(create_teacher_plans, remove_teacher_plans),
    ]
