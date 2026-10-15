from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0031_institute_update_status_index')]

    operations = [
        migrations.AddField('instituteteacher', 'pds_id', models.CharField(blank=True, default='', max_length=64)),
        migrations.AddField('instituteteacher', 'index_no', models.CharField(blank=True, default='', max_length=64)),
        migrations.AddField('instituteteacher', 'district_name', models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField('instituteteacher', 'bcs_batch', models.CharField(blank=True, default='', max_length=64)),
        migrations.AddField('instituteteacher', 'joining_date', models.DateField(blank=True, null=True)),
        migrations.AddField('instituteteacher', 'present_joining_date', models.DateField(blank=True, null=True)),
    ]
