import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .category_normalization import canonical_path, specialized_path
from .catalog_structure import ensure_category
from .models import Category, Product, ProductVariant


class CategoryMeaningTests(SimpleTestCase):
    def test_similar_tv_names_do_not_merge_distinct_product_types(self):
        cases = {
            'Q35 Android TV Box': ('Electronics', 'TV Streaming Boxes'),
            'JPE 32 Frameless Television': ('Electronics', 'Televisions'),
            'HY300 Android Projector': ('Electronics', 'Projectors'),
            'Mini Projector Torch Kids Flashlight': ('Toys & Games', 'Drawing & Projection Toys'),
            'Galaxy Projector Starry Sky Night Light': ('Home & Living', 'Projection Night Lights'),
            'TV Cover 65 inch': ('Home & Living', 'TV Covers'),
        }
        for title, expected in cases.items():
            self.assertEqual(specialized_path(('Electronics', 'TV & Streaming'), title), expected)
        self.assertEqual(canonical_path(('Electronics', 'Smart Watches')), ('Electronics', 'Smartwatches'))


class CategoryConsolidationTests(TestCase):
    databases = {'default', 'ecommerce'}

    def test_merge_preserves_products_cart_prices_alias_filters_and_distinct_counts(self):
        root = Category.objects.create(name='Electronics', slug='electronics')
        old = Category.objects.create(name='Smart Watches', slug='electronics-smart-watches', parent=root)
        current = Category.objects.create(name='Smartwatches', slug='electronics-smartwatches', parent=root)
        product = Product.objects.create(name='Smart Watch', slug='watch', category=old, status='active')
        product.secondary_categories.add(current)
        variant = ProductVariant.objects.create(product=product, sku='watch', price=100, stock=2)
        other = Product.objects.create(name='Another Smartwatch', slug='another-watch', category=current, status='active')
        ProductVariant.objects.create(product=other, sku='another-watch', price=200, stock=1)
        rings = Category.objects.create(name='Smart Rings', slug='electronics-smart-rings', parent=root)
        ring = Product.objects.create(name='Smart Ring', slug='ring', category=rings, status='active',
            attributes={'_catalog_legacy_categories': [old.slug]})
        ProductVariant.objects.create(product=ring, sku='ring', price=50, stock=1)
        client = APIClient()
        cart = client.post('/api/ecommerce/cart/', {'variant_id': variant.pk}, format='json').data
        with tempfile.TemporaryDirectory() as folder:
            def run(name, apply=False):
                path = str(Path(folder) / (name + '.json'))
                call_command('consolidate_catalog_categories', report=path, apply=apply, stdout=StringIO())
                return json.loads(Path(path).with_suffix('.result.json').read_text())
            self.assertEqual(run('preview')['proposed'], 1)
            product.refresh_from_db()
            self.assertEqual(product.category_id, old.pk)
            self.assertEqual(run('apply', True)['changed'], 1)
            self.assertEqual(run('repeat', True)['changed'], 0)
        product.refresh_from_db(); variant.refresh_from_db(); old.refresh_from_db()
        self.assertEqual(product.category_id, current.pk)
        self.assertEqual(product.status, 'active')
        self.assertEqual(variant.price, 100)
        self.assertEqual(Product.objects.count(), 3)
        self.assertFalse(product.secondary_categories.exists())
        self.assertFalse(old.is_active)
        self.assertEqual(client.get('/api/ecommerce/products/?category=' + old.slug).data['count'], 2)
        categories = client.get('/api/ecommerce/categories/').data
        self.assertEqual(next(c['product_count'] for c in categories if c['id'] == root.pk), 3)
        self.assertEqual(client.get('/api/ecommerce/cart/' + cart['token'] + '/').data['items'][0]['variant_id'], variant.pk)
        self.assertEqual(ensure_category(('Electronics', 'Smart Watches')).pk, current.pk)
        old.refresh_from_db()
        self.assertFalse(old.is_active)
