from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0034_institute_refresh_scheduler')]

    operations = [
        migrations.CreateModel(
            name='InstituteRefreshEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('eiin', models.CharField(db_index=True, max_length=6)),
                ('status', models.CharField(max_length=16)),
                ('outcome', models.CharField(blank=True, default='', max_length=32)),
                ('detail', models.CharField(blank=True, default='', max_length=255)),
                ('checked_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={'ordering': ['-checked_at']},
        ),
    ]
