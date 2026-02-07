# Add cheradip_users table for signup form data

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0026_alter_subject_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CheradipUser',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('acctype', models.CharField(choices=[('Student', 'Student'), ('Teacher', 'Teacher'), ('JobSeeker', 'Job Seeker')], db_index=True, default='Student', max_length=10)),
                ('fullName', models.CharField(max_length=31)),
                ('username', models.CharField(db_index=True, max_length=15, unique=True)),
                ('password', models.CharField(max_length=128)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('year_of_birth', models.IntegerField(blank=True, null=True)),
                ('class_name', models.CharField(blank=True, max_length=20, null=True)),
                ('group', models.CharField(blank=True, max_length=30, null=True)),
                ('department', models.CharField(blank=True, max_length=50, null=True)),
                ('teacher_level', models.CharField(blank=True, max_length=20, null=True)),
                ('teacher_subject_code', models.CharField(blank=True, max_length=10, null=True)),
                ('teacher_department_code', models.CharField(blank=True, max_length=20, null=True)),
                ('gender', models.CharField(blank=True, default='Male', max_length=10)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('country_code', models.CharField(db_index=True, max_length=2)),
                ('date_joined', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'cheradip_users',
                'ordering': ['-date_joined'],
                'verbose_name': 'Cheradip User',
                'verbose_name_plural': 'Cheradip Users',
            },
        ),
    ]
