from django.db import migrations, models
import django.db.models.deletion


def set_existing_audience(apps, schema_editor):
    Progress = apps.get_model('cheradip', 'MembershipProgress')
    Progress.objects.filter(account_type__in=['Teacher', 'JobSeeker']).update(audience='teacher')


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0015_package_plan_audience')]

    operations = [
        migrations.AddField(
            model_name='membershipprogress',
            name='audience',
            field=models.CharField(
                choices=[('student', 'Student'), ('teacher', 'Teacher')],
                default='student', max_length=12,
            ),
        ),
        migrations.RunPython(set_existing_audience, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='membershipprogress',
            name='customer',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='membership_progresses',
                to='cheradip.customer',
            ),
        ),
        migrations.AddConstraint(
            model_name='membershipprogress',
            constraint=models.UniqueConstraint(
                fields=('customer', 'audience'), name='unique_membership_progress_audience'
            ),
        ),
    ]
