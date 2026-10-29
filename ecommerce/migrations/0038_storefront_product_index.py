from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('ecommerce', '0037_source_sku_text')]
    operations = [
        migrations.CreateModel(
            name='StorefrontProductIndex',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='storefront_index', serialize=False, to='ecommerce.product')),
                ('name', models.CharField(max_length=255)),
                ('slug', models.SlugField(max_length=255)),
                ('short_description', models.CharField(blank=True, max_length=500)),
                ('search_text', models.CharField(blank=True, max_length=2000)),
                ('category_id', models.IntegerField()),
                ('category_name', models.CharField(blank=True, max_length=160)),
                ('brand_id', models.IntegerField(blank=True, null=True)),
                ('brand_name', models.CharField(blank=True, max_length=160)),
                ('brand_slug', models.SlugField(blank=True, max_length=180)),
                ('featured', models.BooleanField(default=False)),
                ('is_sample', models.BooleanField(default=False)),
                ('tags', models.CharField(blank=True, max_length=1000)),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('compare_at_price', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('stock', models.IntegerField(default=0)),
                ('image_url', models.URLField(blank=True, max_length=1000)),
                ('default_variant_id', models.IntegerField(blank=True, null=True)),
                ('allow_backorder', models.BooleanField(default=False)),
                ('discount_percent', models.PositiveSmallIntegerField(default=0)),
                ('purchasable', models.BooleanField(default=True)),
                ('price_on_request', models.BooleanField(default=False)),
                ('quantity_unspecified', models.BooleanField(default=False)),
                ('listed_at', models.DateTimeField()),
                ('legacy_category_slugs', models.TextField(blank=True)),
            ],
            options={'db_table': 'ecommerce_storefront_product_index', 'ordering': ('-featured', '-listed_at')},
        ),
        migrations.CreateModel(
            name='StorefrontIndexCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='ecommerce.category')),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='browse_categories', to='ecommerce.storefrontproductindex')),
            ],
            options={'db_table': 'ecommerce_storefront_index_category'},
        ),
        migrations.AddIndex(model_name='storefrontproductindex', index=models.Index(fields=['listed_at', 'product'], name='ecommerce_s_listed__idx')),
        migrations.AddIndex(model_name='storefrontproductindex', index=models.Index(fields=['price', 'product'], name='ecommerce_s_price_p_idx')),
        migrations.AddIndex(model_name='storefrontproductindex', index=models.Index(fields=['name', 'product'], name='ecommerce_s_name_pr_idx')),
        migrations.AddIndex(model_name='storefrontproductindex', index=models.Index(fields=['brand_slug'], name='ecommerce_s_brand_s_idx')),
        migrations.AddIndex(model_name='storefrontproductindex', index=models.Index(fields=['featured', 'listed_at'], name='ecommerce_s_feature_idx')),
        migrations.AlterUniqueTogether(name='storefrontindexcategory', unique_together={('listing', 'category')}),
        migrations.AddIndex(model_name='storefrontindexcategory', index=models.Index(fields=['category', 'listing'], name='ecommerce_s_categor_idx')),
    ]
