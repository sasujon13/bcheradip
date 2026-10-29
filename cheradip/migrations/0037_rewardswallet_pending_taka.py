from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0036_live_class_schedule')]
    operations = [
        migrations.AddField(
            model_name='rewardswallet',
            name='pending_taka',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
    ]
