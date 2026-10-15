from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0033_institute_staff_photo')]

    operations = [
        migrations.AddField('instituteupdaterun', 'schedule_month',
                            models.CharField(blank=True, max_length=7, null=True, unique=True)),
        migrations.AddField('instituteupdaterun', 'retry_round',
                            models.PositiveSmallIntegerField(default=0)),
        migrations.AddField('instituteupdaterun', 'retry_cursor',
                            models.CharField(blank=True, default='', max_length=15)),
        migrations.CreateModel(
            name='InstituteRefreshRequest',
            fields=[
                ('eiin', models.CharField(max_length=6, primary_key=True, serialize=False)),
                ('status', models.CharField(default='queued', max_length=16)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('locked_until', models.DateTimeField(blank=True, null=True)),
                ('outcome', models.CharField(blank=True, default='', max_length=32)),
                ('detail', models.CharField(blank=True, default='', max_length=255)),
            ],
            options={'ordering': ['requested_at']},
        ),
    ]
