# Generated migration: add settings JSON field to Customer

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='settings',
            field=models.JSONField(blank=True, default=dict, help_text='User preferences as JSON, e.g. export_format: both|pdf|docx', null=True),
        ),
    ]
