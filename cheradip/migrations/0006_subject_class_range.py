# Add class_range to Subject for storing 9-10, 11-12, 13-16 (one row per subject)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0005_cheradip_prefix_all_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='subject',
            name='class_range',
            field=models.CharField(blank=True, db_index=True, max_length=10, null=True),
        ),
    ]
