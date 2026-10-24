from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0015_supplier_browser_jobs')]
    operations = [
        migrations.AddField(model_name='order', name='cost_snapshot', field=models.JSONField(blank=True, default=dict, editable=False)),
        migrations.AddField(model_name='deliverysettings', name='delivery_subsidy_enabled', field=models.BooleanField(default=False, help_text='Opt in to adding a supplier/customer delivery shortfall to new listing-price suggestions. Existing order prices never change.')),
        migrations.AddField(model_name='product', name='supplier_delivery_rates', field=models.JSONField(blank=True, default=dict, help_text='Verified supplier delivery tariff: dhaka/outside lists of {up_to_grams, charge}. Charged directly, without a midpoint or subsidy. Optional shipment_group permits confirmed consolidation only.')),
    ]
