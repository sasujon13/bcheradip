from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0033_cartitem_requested_size')]
    operations = [
        migrations.AddField(model_name='cartitem', name='requested_color',
                            field=models.CharField(max_length=40, blank=True, default='')),
        migrations.RemoveConstraint(model_name='cartitem', name='ecommerce_cart_variant_size_unique'),
        migrations.AddConstraint(model_name='cartitem', constraint=models.UniqueConstraint(
            fields=['cart', 'variant', 'requested_size', 'requested_color'],
            name='ecommerce_cart_variant_choices_unique')),
    ]
