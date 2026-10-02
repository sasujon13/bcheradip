from django.db import migrations, models
import django.db.models.deletion


def preserve_existing_metric_counts(apps, schema_editor):
    progress = apps.get_model('cheradip', 'MembershipProgress')
    for row in progress.objects.all().only('id', 'metric_count'):
        progress.objects.filter(pk=row.pk).update(raw_metric_count=row.metric_count)


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0012_package_lifecycle_profile_image')]

    operations = [
        migrations.AddField(
            model_name='customer', name='referred_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='referred_customers', to='cheradip.customer'),
        ),
        migrations.AddField(model_name='membershipprogress', name='raw_metric_count', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='membershipprogress', name='metric_offset', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='membershipprogress', name='maintenance_penalty_active', field=models.BooleanField(default=False)),
        migrations.RunPython(preserve_existing_metric_counts, migrations.RunPython.noop),
        migrations.CreateModel(
            name='ReferralCommission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gross_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('reference_value_percent', models.PositiveSmallIntegerField(default=0)),
                ('commission_coins', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('referred_customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='generated_referral_commissions', to='cheradip.customer')),
                ('referrer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referral_commissions', to='cheradip.customer')),
                ('subscription', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='referral_commission', to='cheradip.packagesubscription')),
            ],
            options={'db_table': 'cheradip_referral_commissions', 'ordering': ['-created_at']},
        ),
    ]
