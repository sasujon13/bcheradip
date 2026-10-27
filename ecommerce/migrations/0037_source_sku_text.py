from django.db import migrations,models


class Migration(migrations.Migration):
    dependencies=[('ecommerce','0036_catalog_sync_identity_and_unique')]
    operations=[migrations.AlterField(model_name='suppliersourceproduct',name='sku',field=models.TextField(blank=True))]
