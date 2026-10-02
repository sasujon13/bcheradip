from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0011_seed_package_plans')]

    operations = [
        migrations.AddField(
            model_name='customer', name='profile_image',
            field=models.ImageField(blank=True, null=True, upload_to='profiles/%Y/%m/'),
        ),
        migrations.AddField(model_name='membershipprogress', name='base', field=models.CharField(default='New', max_length=20)),
        migrations.AlterField(
            model_name='packagesubscription', name='status',
            field=models.CharField(choices=[('pending', 'Pending payment'), ('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled'), ('superseded', 'Superseded'), ('grace', 'Payment grace period')], db_index=True, default='pending', max_length=20),
        ),
        migrations.AddField(model_name='packagesubscription', name='auto_renew', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='packagesubscription', name='next_renewal_at', field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='packagesubscription', name='last_renewal_attempt_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='packagesubscription', name='renewal_failed_attempts', field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name='packagesubscription', name='grace_started_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='packagesubscription', name='grace_ends_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='packagesubscription', name='last_warning_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='packagesubscription', name='renewal_failure_reason', field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='packagesubscription', name='superseded_at', field=models.DateTimeField(blank=True, null=True)),
    ]
