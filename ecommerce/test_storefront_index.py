from django.test import TestCase
from rest_framework.test import APIClient
from .models import Category, Product, ProductImage, ProductVariant, StorefrontLastUsedCategory, StorefrontProductIndex, StorefrontTaxonomySnapshot
from .storefront_index import flush_index_refresh, refresh_storefront_index
from .storefront_taxonomy import remember_last_used, refresh_taxonomy_snapshot


class StorefrontIndexTests(TestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.category = Category.objects.using('ecommerce').create(name='General', slug='general-index')
        self.child = Category.objects.using('ecommerce').create(name='Lights', slug='lights-index', parent=self.category)
        self.product = Product.objects.using('ecommerce').create(
            name='Index Lamp', slug='index-lamp', status='active', category=self.child,
            short_description='Bright lamp text')
        self.variant = ProductVariant.objects.using('ecommerce').create(
            product=self.product, sku='INDEX-LAMP', title='Default', price=288, stock=5)
        ProductImage.objects.using('ecommerce').create(
            product=self.product, url='https://cdn.example.com/lamp.jpg', position=0)
        flush_index_refresh()
        self.client = APIClient()
        self.client.credentials(HTTP_X_FORWARDED_PROTO='https')

    def test_listing_uses_index_text_and_keeps_image_url(self):
        refresh_storefront_index([self.product.pk])
        row = StorefrontProductIndex.objects.using('ecommerce').get(pk=self.product.pk)
        self.assertEqual(row.name, 'Index Lamp')
        self.assertEqual(row.short_description, 'Bright lamp text')
        self.assertEqual(str(row.price), '288.00')
        listing = self.client.get('/api/ecommerce/products/?category=general-index')
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertGreaterEqual(listing.data['count'], 1)
        card = next(item for item in listing.data['results'] if item['slug'] == 'index-lamp')
        self.assertEqual(card['name'], 'Index Lamp')
        self.assertEqual(card['category_name'], 'Lights')
        self.assertTrue(card['image_url'])

    def test_child_category_browse_uses_index_membership(self):
        refresh_storefront_index([self.product.pk])
        child = self.client.get('/api/ecommerce/products/?category=lights-index')
        self.assertEqual(child.data['count'], 1)
        self.assertEqual(child.data['results'][0]['name'], 'Index Lamp')

    def test_category_list_uses_index_snapshot_and_rolls_up_parent_counts(self):
        refresh_storefront_index([self.product.pk])
        payload = refresh_taxonomy_snapshot()
        self.assertTrue(payload['categories'])
        row = StorefrontTaxonomySnapshot.objects.using('ecommerce').get(key='storefront')
        self.assertEqual(row.payload['categories'][0]['slug'], payload['categories'][0]['slug'])
        response = self.client.get('/api/ecommerce/categories/')
        by_slug = {item['slug']: item for item in response.data}
        self.assertEqual(by_slug['lights-index']['product_count'], 1)
        self.assertEqual(by_slug['general-index']['product_count'], 1)

    def test_listing_a_category_reserves_parent_and_related_subcategories(self):
        extra = Category.objects.using('ecommerce').create(name='Cables', slug='cables-index', parent=self.category)
        listing = self.client.get('/api/ecommerce/products/?category=lights-index')
        self.assertEqual(listing.status_code, 200, listing.data)
        slugs = set(StorefrontLastUsedCategory.objects.using('ecommerce').values_list('slug', flat=True))
        self.assertEqual(slugs, {'general-index', 'lights-index', extra.slug})
        parent = StorefrontLastUsedCategory.objects.using('ecommerce').get(slug='general-index')
        self.assertIn('lights-index', parent.child_slugs)
        self.assertIn(extra.slug, parent.child_slugs)

    def test_empty_snapshot_warms_from_live_taxonomy(self):
        StorefrontProductIndex.objects.using('ecommerce').all().delete()
        StorefrontTaxonomySnapshot.objects.using('ecommerce').all().delete()
        remember_last_used('general-index')
        response = self.client.get('/api/ecommerce/categories/')
        by_slug = {item['slug']: item for item in response.data}
        self.assertEqual(by_slug['general-index']['product_count'], 1)
        self.assertTrue(StorefrontTaxonomySnapshot.objects.using('ecommerce').filter(key='storefront').exists())
