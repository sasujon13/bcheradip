from django.db import migrations, models


def populate_package_order_numbers(apps, schema_editor):
    subscription_model = apps.get_model('cheradip', 'PackageSubscription')
    for subscription in subscription_model.objects.filter(order_number__isnull=True).iterator():
        subscription.order_number = f'PKG-HIST-{subscription.pk:010d}'
        subscription.save(update_fields=['order_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('cheradip', '0021_alter_customer_acctype'),
    ]

    operations = [
        migrations.AddField(
            model_name='packagesubscription',
            name='order_number',
            field=models.CharField(blank=True, db_index=True, max_length=32, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='packagesubscription',
            name='order_status',
            field=models.CharField(
                choices=[
                    ('completed', 'Order Completed'),
                    ('cancelled', 'Order Cancelled'),
                    ('refunded', 'Order Refunded'),
                ],
                db_index=True,
                default='completed',
                max_length=20,
            ),
        ),
        migrations.RunPython(populate_package_order_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='packagesubscription',
            name='order_number',
            field=models.CharField(blank=True, db_index=True, max_length=32, unique=True),
        ),
    ]
