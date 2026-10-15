from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0030_institute_update_runs')]

    operations = [
        migrations.AddIndex(
            model_name='instituteupdateattempt',
            index=models.Index(fields=['run', 'status'], name='institute_run_status_idx'),
        ),
    ]
