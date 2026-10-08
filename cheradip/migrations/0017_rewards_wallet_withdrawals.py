from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def backfill_rewards_wallets(apps, schema_editor):
    from django.db.models import Sum

    Customer = apps.get_model('cheradip', 'Customer')
    ReferralCommission = apps.get_model('cheradip', 'ReferralCommission')
    RewardsWallet = apps.get_model('cheradip', 'RewardsWallet')
    totals = {
        row['referrer_id']: Decimal(row['coins'] or 0) / Decimal('100')
        for row in ReferralCommission.objects.values('referrer_id').annotate(coins=Sum('commission_coins'))
    }
    for customer_id, amount in totals.items():
        RewardsWallet.objects.update_or_create(
            customer_id=customer_id,
            defaults={'available_taka': amount, 'lifetime_earned_taka': amount},
        )


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0016_membership_progress_audience')]

    operations = [
        migrations.CreateModel(
            name='RewardsWallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('available_taka', models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('lifetime_earned_taka', models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('lifetime_withdrawn_taka', models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='rewards_wallet', to='cheradip.customer')),
            ],
            options={'db_table': 'cheradip_rewards_wallet'},
        ),
        migrations.CreateModel(
            name='WithdrawalRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('method', models.CharField(choices=[('bkash', 'bKash'), ('nagad', 'Nagad'), ('dbbl', 'DBBL / Rocket'), ('sonali', 'Sonali Bank')], max_length=16)),
                ('account_name', models.CharField(blank=True, max_length=100)),
                ('account_number', models.CharField(max_length=64)),
                ('amount_taka', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(100)])),
                ('balance_before_taka', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('balance_after_taka', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing / payment started'), ('approved', 'Approved / Paid'), ('rejected', 'Rejected'), ('cancelled', 'Cancelled by user')], db_index=True, default='pending', max_length=16)),
                ('admin_note', models.TextField(blank=True)),
                ('requested_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='withdrawal_requests', to='cheradip.customer')),
                ('processed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_withdrawal_requests', to='cheradip.customer')),
            ],
            options={'db_table': 'cheradip_withdrawal_requests', 'ordering': ['-requested_at']},
        ),
        migrations.AddIndex(
            model_name='withdrawalrequest',
            index=models.Index(fields=['customer', 'status', 'requested_at'], name='cheradip_wi_custome_ff8db9_idx'),
        ),
        migrations.RunPython(backfill_rewards_wallets, migrations.RunPython.noop),
    ]
