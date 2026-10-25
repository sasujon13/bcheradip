from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0032_deliverysettings_pricing_rules')]
    operations = [
        migrations.AddField(model_name='cartitem', name='requested_size',
                            field=models.CharField(max_length=40, blank=True, default='')),
        migrations.RemoveConstraint(model_name='cartitem', name='ecommerce_cart_variant_unique'),
        migrations.AddConstraint(model_name='cartitem', constraint=models.UniqueConstraint(
            fields=['cart', 'variant', 'requested_size'], name='ecommerce_cart_variant_size_unique')),
    ]
