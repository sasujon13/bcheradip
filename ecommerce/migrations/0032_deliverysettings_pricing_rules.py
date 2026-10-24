from django.db import migrations,models
import ecommerce.pricing

class Migration(migrations.Migration):
    dependencies=[('ecommerce','0031_labelled_stock_connector')]
    operations=[migrations.AddField(model_name='deliverysettings',name='pricing_rules',
        field=models.JSONField(default=ecommerce.pricing.default_pricing_rules,
            help_text='Central all-cost markup bands and automatic sale-discount percentage. Apply existing supplier prices explicitly in Manage.'))]
