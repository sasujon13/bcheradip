from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0038_storefront_product_index')]
    operations = [
        migrations.CreateModel(
            name='StorefrontTaxonomySnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.CharField(max_length=32, unique=True)),
                ('payload', models.JSONField(default=dict)),
            ],
            options={'db_table': 'ecommerce_storefront_taxonomy_snapshot'},
        ),
        migrations.CreateModel(
            name='StorefrontLastUsedCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=180, unique=True)),
                ('name', models.CharField(max_length=160)),
                ('parent_slug', models.SlugField(max_length=180, blank=True)),
                ('child_slugs', models.JSONField(default=list)),
                ('used_at', models.DateTimeField(db_index=True)),
            ],
            options={'db_table': 'ecommerce_storefront_last_used_category', 'ordering': ('-used_at',)},
        ),
    ]
