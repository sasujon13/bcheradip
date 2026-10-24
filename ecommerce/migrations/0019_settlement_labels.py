from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0018_supplier_settlements')]
    operations = [migrations.AlterModelOptions(name='suppliersettlemententry', options={'ordering': ('-created_at',), 'verbose_name_plural': 'Supplier settlement entries'})]
