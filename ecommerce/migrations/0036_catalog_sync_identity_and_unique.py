from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0035_product_secondary_categories')]
    operations = [
        migrations.CreateModel(name='CatalogSyncIdentity', fields=[
            ('uid', models.UUIDField(primary_key=True, serialize=False)),
            ('model_name', models.CharField(max_length=60)),
            ('object_pk', models.CharField(max_length=60)),
            ('field_hashes', models.JSONField(default=dict)),
        ], options={'constraints': [models.UniqueConstraint(fields=('model_name','object_pk'), name='catalog_sync_local_object')]}),
        migrations.AlterField(model_name='supplieroffer', name='state', field=models.CharField(max_length=25, db_index=True,
            default='collected', choices=[(x,x.replace('_',' ').title()) for x in
            ('collected','needs_data','needs_review','ready','reduced_margin','blacklist','zero_margin','excluded','unique')])),
    ]
