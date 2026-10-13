from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0027_recovery_and_recharge_identity')]

    operations = [
        migrations.CreateModel(
            name='InstituteSourceSnapshot',
            fields=[
                ('eiin', models.CharField(max_length=15, primary_key=True, serialize=False)),
                ('banbeis', models.JSONField(blank=True, default=dict)),
                ('emis', models.JSONField(blank=True, default=dict)),
                ('last_banbeis_sync_at', models.DateTimeField(blank=True, null=True)),
                ('last_emis_sync_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['eiin']},
        ),
        migrations.CreateModel(
            name='InstituteScrapePage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('page', models.PositiveIntegerField()),
                ('size', models.PositiveSmallIntegerField()),
                ('source', models.CharField(default='banbeis', max_length=32)),
                ('created', models.PositiveSmallIntegerField(default=0)),
                ('updated', models.PositiveSmallIntegerField(default=0)),
                ('unchanged', models.PositiveSmallIntegerField(default=0)),
                ('failed', models.PositiveSmallIntegerField(default=0)),
                ('source_total', models.PositiveIntegerField(default=0)),
                ('processed_at', models.DateTimeField(auto_now=True)),
                ('processed_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='cheradip.customer')),
            ],
            options={'ordering': ['-processed_at']},
        ),
        migrations.AddConstraint(
            model_name='institutescrapepage',
            constraint=models.UniqueConstraint(fields=('source', 'page', 'size'), name='unique_institute_scrape_page'),
        ),
    ]
