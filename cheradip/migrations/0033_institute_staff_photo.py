from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0032_institute_staff_details')]

    operations = [
        migrations.AddField('instituteteacher', 'photo_url', models.CharField(blank=True, default='', max_length=500)),
    ]
