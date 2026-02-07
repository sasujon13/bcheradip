# Add teacher_department_name for custom "Others" department (Teacher University signup).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0033_cheradip_teacher_and_cheradip_users'),
    ]

    operations = [
        migrations.AddField(
            model_name='cheradipteacher',
            name='teacher_department_name',
            field=models.CharField(blank=True, help_text='Custom department name when code is OTHER', max_length=200, null=True),
        ),
    ]
