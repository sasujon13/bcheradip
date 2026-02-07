# Remove year_of_birth from cheradip_users (can be derived from date_of_birth)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0027_add_cheradip_users'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cheradipuser',
            name='year_of_birth',
        ),
    ]
