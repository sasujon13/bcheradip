from io import BytesIO
from pathlib import Path
import tempfile

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from cheradip.models import Customer, CustomerToken
from .models import Category, InventoryMovement, Product, ProductVariant


class CommerceManagementTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='manage-test', password='test-only', fullName='Manager')
        CustomerToken.objects.create(key='manage-test-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer manage-test-token', HTTP_X_FORWARDED_PROTO='https')
        self.category = Category.objects.using('ecommerce').create(name='Test category', slug='manage-category')

    def staff(self, superuser=False):
        self.user.is_staff = True
        self.user.is_superuser = superuser
        self.user.save(update_fields=['is_staff', 'is_superuser'])

    def grant(self, model, action):
        content_type, _ = ContentType.objects.get_or_create(app_label='ecommerce', model=model._meta.model_name)
        permission, _ = Permission.objects.get_or_create(content_type=content_type,
            codename=f'{action}_{model._meta.model_name}', defaults={'name': 'Management test permission'})
        self.user.user_permissions.add(permission)

    def payload(self, slug='own-product'):
        return {'name': 'Own product', 'slug': slug, 'category': self.category.pk, 'status': 'active',
                'variants': [{'title': 'Blue / M', 'sku': slug.upper(), 'price': '125.00', 'stock': 8}],
                'images': [{'url': 'https://example.com/product.png', 'position': 0, 'alt_text': 'Own product'}]}

    def test_anonymous_and_regular_users_have_no_management_access(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_FORWARDED_PROTO='https')
        self.assertFalse(anonymous.get('/api/ecommerce/admin/access/').json()['allowed'])
        self.assertFalse(self.client.get('/api/ecommerce/admin/access/').json()['allowed'])
        for endpoint in ['products', 'orders', 'payments', 'variants', 'categories', 'brands', 'coupons', 'shipments', 'reviews', 'imports', 'notifications']:
            self.assertIn(self.client.get(f'/api/ecommerce/admin/{endpoint}/').status_code, (401, 403))
        self.assertIn(self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json').status_code, (401, 403))
        self.assertEqual(Product.objects.using('ecommerce').count(), 0)

    def test_staff_permissions_are_not_implied_by_staff_flag(self):
        self.staff()
        access = self.client.get('/api/ecommerce/admin/access/').json()
        self.assertTrue(access['allowed'])
        self.assertFalse(access['permissions']['product']['add'])
        self.assertEqual(self.client.get('/api/ecommerce/admin/products/').status_code, 403)
        self.assertEqual(self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json').status_code, 403)

    def test_bearer_admin_creates_and_updates_complete_product_and_stock_audit(self):
        self.staff(superuser=True)
        created = self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json')
        self.assertEqual(created.status_code, 201, created.data)
        product = created.json()
        self.assertEqual(len(product['variants']), 1)
        self.assertEqual(len(product['images']), 1)
        self.assertEqual(InventoryMovement.objects.using('ecommerce').get().quantity, 8)
        variant = product['variants'][0]
        variant['stock'] = 5
        updated = self.client.patch(f"/api/ecommerce/admin/products/{product['id']}/", {'variants': [variant]}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.json()['variants'][0]['stock'], 5)
        self.assertEqual(InventoryMovement.objects.using('ecommerce').order_by('-id').first().quantity, -3)

    def test_nested_write_requires_variant_permissions_and_is_atomic(self):
        self.staff()
        self.grant(Product, 'add')
        denied = self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json')
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertEqual(Product.objects.using('ecommerce').count(), 0)

    def test_duplicate_sku_and_foreign_variant_cannot_mutate_other_products(self):
        self.staff(superuser=True)
        first = self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json').json()
        second = self.payload('second')
        second['variants'][0]['sku'] = 'OWN-PRODUCT'
        self.assertEqual(self.client.post('/api/ecommerce/admin/products/', second, format='json').status_code, 400)
        second['variants'][0]['sku'] = 'SECOND'
        second['variants'][0]['id'] = first['variants'][0]['id']
        self.assertEqual(self.client.post('/api/ecommerce/admin/products/', second, format='json').status_code, 400)
        self.assertEqual(Product.objects.using('ecommerce').count(), 1)
        self.assertEqual(ProductVariant.objects.using('ecommerce').get().stock, 8)

    def test_stock_adjustment_rejects_invalid_or_negative_result(self):
        self.staff(superuser=True)
        created = self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json').json()
        for quantity in ['bad', '1.5', 0, -9]:
            result = self.client.post('/api/ecommerce/admin/inventory/', {'variant_id': created['variants'][0]['id'], 'quantity': quantity}, format='json')
            self.assertEqual(result.status_code, 400, result.data)
        self.assertEqual(ProductVariant.objects.using('ecommerce').get().stock, 8)

    def test_upload_is_staff_only_and_reencodes_images(self):
        self.staff(superuser=True)
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            invalid = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')
            self.assertEqual(self.client.post('/api/ecommerce/admin/upload-image/', {'file': invalid}).status_code, 400)
            image = BytesIO()
            Image.new('RGB', (80, 60), 'teal').save(image, format='PNG')
            valid = SimpleUploadedFile('own-product.png', image.getvalue(), content_type='image/png')
            response = self.client.post('/api/ecommerce/admin/upload-image/', {'file': valid})
            self.assertEqual(response.status_code, 201, response.data)
            self.assertTrue(response.json()['url'].startswith('/manage/media/ecommerce/products/'))
            payload = self.payload()
            payload['images'][0]['url'] = response.json()['url']
            created = self.client.post('/api/ecommerce/admin/products/', payload, format='json')
            self.assertEqual(created.status_code, 201, created.data)
            self.assertEqual(created.json()['images'][0]['url'], response.json()['url'])
            self.assertEqual(len(list(Path(folder).rglob('*.webp'))), 1)

    def test_category_cycle_and_invalid_coupon_are_rejected(self):
        self.staff(superuser=True)
        response = self.client.patch(f'/api/ecommerce/admin/categories/{self.category.pk}/', {'parent': self.category.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/ecommerce/admin/coupons/', {'code': 'TOO-MUCH', 'discount_type': 'percent', 'value': '150'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_session_auth_still_requires_csrf_and_invalid_bearer_cannot_fall_back(self):
        self.staff(superuser=True)
        session_client = APIClient(enforce_csrf_checks=True)
        session_client.force_login(self.user)
        session_client.credentials(HTTP_X_FORWARDED_PROTO='https')
        self.assertTrue(session_client.get('/api/ecommerce/admin/access/').json()['allowed'])
        self.assertEqual(session_client.post('/api/ecommerce/admin/products/', self.payload(), format='json').status_code, 403)
        session_client.credentials(HTTP_X_FORWARDED_PROTO='https', HTTP_AUTHORIZATION='Bearer invalid-test-token')
        self.assertEqual(session_client.get('/api/ecommerce/admin/access/').status_code, 401)
        regular = Customer.objects.create_user(username='ordinary-test', password='test-only')
        CustomerToken.objects.create(key='ordinary-test-token', customer=regular)
        session_client.credentials(HTTP_X_FORWARDED_PROTO='https', HTTP_AUTHORIZATION='Bearer ordinary-test-token')
        self.assertFalse(session_client.get('/api/ecommerce/admin/access/').json()['allowed'])
        self.assertEqual(session_client.post('/api/ecommerce/admin/products/', self.payload(), format='json').status_code, 403)

    def test_stock_conflict_is_atomic_and_partial_variant_edits_preserve_stock(self):
        self.staff(superuser=True)
        product = self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json').json()
        variant_id = product['variants'][0]['id']
        ProductVariant.objects.using('ecommerce').filter(pk=variant_id).update(stock=6)
        response = self.client.patch(f"/api/ecommerce/admin/products/{product['id']}/", {
            'name': 'Stale product edit', 'variants': [{'id': variant_id, 'stock': 10, 'expected_stock': 8}],
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Product.objects.using('ecommerce').get(pk=product['id']).name, 'Own product')
        response = self.client.patch(f"/api/ecommerce/admin/products/{product['id']}/", {
            'variants': [{'id': variant_id, 'title': 'New title'}],
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.json()['variants'][0]['stock'], 6)
        for row in [{'sku': 'NEW'}, {'price': 4}, {'id': variant_id, 'price': -1}, {'id': variant_id, 'cost_price': -2}]:
            response = self.client.patch(f"/api/ecommerce/admin/products/{product['id']}/", {'variants': [row]}, format='json')
            self.assertEqual(response.status_code, 400, response.data)

    def test_unrelated_edits_preserve_photos_and_removed_variants_are_deactivated(self):
        self.staff(superuser=True)
        product = self.client.post('/api/ecommerce/admin/products/', self.payload(), format='json').json()
        self.client.patch(f"/api/ecommerce/admin/products/{product['id']}/", {'name': 'Renamed'}, format='json')
        response = self.client.get(f"/api/ecommerce/admin/products/{product['id']}/")
        self.assertEqual(len(response.json()['images']), 1)
        response = self.client.patch(f"/api/ecommerce/admin/products/{product['id']}/", {'variants': []}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProductVariant.objects.using('ecommerce').count(), 1)
        self.assertFalse(ProductVariant.objects.using('ecommerce').get().is_active)
