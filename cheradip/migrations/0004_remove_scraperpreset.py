# Remove ScraperPreset model and cheradip_scraper_preset table.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0003_drop_cheradip_subject_translated'),
    ]

    operations = [
        migrations.DeleteModel(name='ScraperPreset'),
    ]
