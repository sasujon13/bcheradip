import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .category_normalization import canonical_path, specialized_path
from .category_suggestion_rules import (
    beauty_destination, clothing_destination, electronics_destination, kids_destination,
)
from .catalog_structure import ensure_category
from .catalog_structure import classify
from .models import Category, Product, ProductVariant


class CategoryMeaningTests(SimpleTestCase):
    def test_similar_tv_names_do_not_merge_distinct_product_types(self):
        cases = {
            'Q35 Android TV Box': ('Electronics', 'TV Streaming Boxes'),
            'JPE 32 Frameless Television': ('Electronics', 'Televisions'),
            'HY300 Android Projector': ('Electronics', 'Projectors'),
            'Mini Projector Torch Kids Flashlight': ('Kids & Baby', 'Drawing & Projection Toys'),
            'Galaxy Projector Starry Sky Night Light': ('Home & Living', 'Projection Night Lights'),
            'TV Cover 65 inch': ('Home & Living', 'TV Covers'),
        }
        for title, expected in cases.items():
            self.assertEqual(specialized_path(('Electronics', 'TV & Streaming'), title), expected)
        self.assertEqual(canonical_path(('Electronics', 'Smart Watches')), ('Electronics', 'Smartwatches'))
        self.assertEqual(canonical_path(('Computer & Accessories', 'Keyboards')), ('Electronics', 'Keyboards'))
        self.assertEqual(canonical_path(('Automotive', 'Vehicle Accessories')), ('Tools & Home Improvement', 'Vehicle Accessories'))
        self.assertEqual(canonical_path(('Office & Stationary', 'Notebooks')), ('Electronics', 'Notebooks'))
        self.assertEqual(canonical_path(('Watches & Accessories', 'Wristwatches')), ('Watches & Jewelry', 'Wrist Watches'))
        self.assertEqual(canonical_path(('Pet Supplies', 'Pet Care')), ('Home & Living', 'Aquarium Supplies'))
        self.assertEqual(canonical_path(('Pet Supplies',)), ('Home & Living',))
        self.assertEqual(canonical_path(('Kids & Toys',)), ('Kids & Baby',))
        self.assertEqual(canonical_path(('Kids & Toys', 'Toys & Games')), ('Kids & Baby', 'Toys'))
        self.assertEqual(canonical_path(('Toys & Games', 'Drawing & Projection Toys')),
                         ('Kids & Baby', 'Drawing & Projection Toys'))
        self.assertEqual(canonical_path(('Mobile & Accessories', 'Phone Chargers')),
                         ('Electronics', 'Phone Chargers'))
        self.assertEqual(canonical_path(('Mobile & Accessories', 'Phone Cases')),
                         ('Electronics', 'Phone Cases & Accessories'))
        self.assertEqual(canonical_path(('Digital Services', 'Software & Services')), ('Digital Services',))
        self.assertEqual(canonical_path(('Food & Groceries', 'Food & Drinks')), ('Food & Groceries',))
        self.assertEqual(canonical_path(('Food & Health', 'Food & Drinks')), ('Food & Groceries',))

    def test_generic_dresses_do_not_reappear_on_import(self):
        result = classify('Beautiful dress', categories=['Dresses'])
        self.assertNotEqual(result.get('path'), ['Clothing', 'Dresses'])
        self.assertIn(result['status'], ('assigned', 'needs_review'))

    def test_suggestion_classifiers_use_existing_types_and_skip_jewelry(self):
        self.assertEqual(kids_destination('বেবি ডায়াপার', assume_kids=True), ('Kids & Baby', 'Diapers'))
        self.assertEqual(kids_destination('Super Soft Cotton Fleece Baby Hoodie'),
                         ('Kids & Baby', "Children's Hoodies"))
        self.assertEqual(kids_destination('Super Car Die-Cast Metal Set', assume_kids=True),
                         ('Kids & Baby', 'Toys'))
        self.assertEqual(kids_destination('Half Sleeve T-shirt and Pant Set. সাইজ ৬ মাস - ১৩ বছর'),
                         ('Kids & Baby', "Children's Matching Sets"))
        self.assertIsNone(kids_destination('Exclusive Baby Pink Cotton Embroidered Three Piece'))
        self.assertEqual(electronics_destination('Joyroom JR-PBF12 10000mAh Power Bank'),
                         ('Electronics', 'Power Banks'))
        self.assertEqual(electronics_destination('Awei T230 ANC Pro True Wireless Earbuds'),
                         ('Electronics', 'Wireless Earbuds'))
        self.assertEqual(electronics_destination('V380 Pro Dual Lens WiFi Security Camera'),
                         ('Electronics', 'Security Cameras'))
        self.assertEqual(clothing_destination('Premium Aarong Cotton Readymade Three-Piece'),
                         ("Women's Fashion", 'Three-Piece Sets'))
        self.assertEqual(clothing_destination("Men's Stylish Premium Drop Shoulder"),
                         ("Men's Fashion", 'T-Shirts'))
        self.assertIsNone(clothing_destination('Exclusive Gorgeous Gold-Plated Kundan Necklace'))
        self.assertIsNone(clothing_destination('vintage glasses men & Women'))
        self.assertEqual(beauty_destination('Missha All Around Safe Block Aqua Sun Gel SPF50+/PA++++'),
                         ('Beauty & Personal Care', 'Sunscreens'))
        self.assertEqual(beauty_destination('Simple Kind to Skin Refreshing Facial Gel Wash'),
                         ('Beauty & Personal Care', 'Face Washes'))
        self.assertIsNone(beauty_destination('Adjustable Knee Brace'))


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
