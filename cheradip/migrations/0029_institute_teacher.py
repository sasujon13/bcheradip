from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0028_institute_scraper')]

    operations = [
        migrations.CreateModel(
            name='InstituteTeacher',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('eiin', models.CharField(db_index=True, max_length=15)),
                ('source_row_id', models.CharField(max_length=64)),
                ('name', models.CharField(max_length=255)),
                ('name_bn', models.CharField(blank=True, default='', max_length=255)),
                ('designation', models.CharField(blank=True, default='', max_length=255)),
                ('subject', models.CharField(blank=True, default='', max_length=255)),
                ('mobile', models.CharField(blank=True, default='', max_length=32)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('position', models.PositiveSmallIntegerField(default=0)),
                ('listed', models.BooleanField(default=True)),
                ('last_seen_at', models.DateTimeField()),
            ],
            options={'ordering': ['eiin', 'position', 'id']},
        ),
        migrations.AddConstraint(
            model_name='instituteteacher',
            constraint=models.UniqueConstraint(fields=('eiin', 'source_row_id'), name='unique_emis_teacher_per_eiin'),
        ),
    ]
