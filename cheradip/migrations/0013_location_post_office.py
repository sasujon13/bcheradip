# Add post_office to Location (before post_code in display order)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0012_location_country_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='location',
            name='post_office',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
