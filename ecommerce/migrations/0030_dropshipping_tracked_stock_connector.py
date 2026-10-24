from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0029_reseller_tracked_stock_connector')]
    operations = [migrations.AlterField(
        model_name='supplier', name='connector',
        field=models.CharField(max_length=40, default='snapshot', choices=[
            ('snapshot', 'Authorised JSON snapshot'),
            ('business_koro', 'Business Koro storefront API (read only)'),
            ('uddoog', 'Uddoog account price/stock API (read only)'),
            ('resellkori', 'ResellKori tracked price/stock (read only)'),
            ('dropshipping_bd', 'Dropshipping.com.bd tracked price/stock (read only)')]))]
