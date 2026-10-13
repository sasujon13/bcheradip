from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0026_admintablefingerprint')]

    operations = [
        migrations.CreateModel(
            name='VerificationChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('purpose', models.CharField(max_length=24)),
                ('code_hash', models.CharField(max_length=128)),
                ('expires_at', models.DateTimeField()),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='verification_challenges', to=settings.AUTH_USER_MODEL)),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('customer', 'purpose'), name='customer_verification_purpose_unique')]},
        ),
        migrations.AddField(
            model_name='trxmanagement', name='verified',
            field=models.BooleanField(default=False, help_text='Trusted payment source or manually checked receipt.'),
        ),
        migrations.CreateModel(
            name='TrxIdentity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trxid', models.CharField(max_length=128, unique=True)),
                ('transaction', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='identity', to='cheradip.trxmanagement')),
            ],
        ),
    ]
