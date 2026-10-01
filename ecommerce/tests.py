import csv
import io

from django.test import SimpleTestCase, TransactionTestCase
from rest_framework.test import APIClient

from .csv_import import CSV_COLUMNS, sample_csv_text
from .db_router import EcommerceRouter
from .models import Category, Order, Product, ProductVariant


class EcommerceConfigurationTests(SimpleTestCase):
    def test_router_keeps_commerce_in_its_own_database(self):
        router = EcommerceRouter()
        self.assertEqual(router.db_for_read(Product), 'ecommerce')
        self.assertEqual(router.db_for_write(Product), 'ecommerce')
        self.assertTrue(router.allow_migrate('ecommerce', 'ecommerce'))
        self.assertFalse(router.allow_migrate('default', 'ecommerce'))

    def test_sample_csv_is_ready_to_import(self):
        rows = list(csv.DictReader(io.StringIO(sample_csv_text())))
        self.assertEqual(list(rows[0]), CSV_COLUMNS)
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(all(row['Handle'] and row['SKU'] and row['Price'] for row in rows))


class StorefrontFlowTests(TransactionTestCase):
    databases = {'ecommerce'}
    reset_sequences = True

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_FORWARDED_PROTO='https')
        category = Category.objects.using('ecommerce').create(name='Electronics', slug='electronics')
        product = Product.objects.using('ecommerce').create(
            name='Test Device', slug='test-device', category=category, status='active',
            short_description='A test storefront product.',
        )
        self.variant = ProductVariant.objects.using('ecommerce').create(
            product=product, title='Default', sku='TEST-001', price='1200.00', stock=5,
            low_stock_threshold=1, requires_shipping=True,
        )

    def test_cart_checkout_tracks_order_and_prices_shipping_on_server(self):
        cart_response = self.client.post('/api/ecommerce/cart/', {
            'variant_id': self.variant.pk, 'quantity': 2,
        }, format='json')
        self.assertEqual(cart_response.status_code, 200)
        cart = cart_response.json()
        self.assertEqual(cart['subtotal'], 2400.0)

        checkout_response = self.client.post('/api/ecommerce/checkout/', {
            'cart_token': cart['token'], 'customer_name': 'Test Customer',
            'email': 'customer@example.com', 'phone': '01700000000',
            'shipping_address': {'address': 'Test Road', 'city': 'Dhaka'},
            'shipping_total': '0.00',
        }, format='json')
        self.assertEqual(checkout_response.status_code, 201)
        order = checkout_response.json()
        self.assertEqual(order['shipping_total'], '80.00')
        self.assertEqual(order['grand_total'], '2480.00')

        tracking_response = self.client.get(
            f"/api/ecommerce/orders/{order['number']}/",
            {'tracking_token': order['tracking_token']},
        )
        self.assertEqual(tracking_response.status_code, 200)
        self.assertEqual(tracking_response.json()['number'], order['number'])
        email_only_response = self.client.get(
            f"/api/ecommerce/orders/{order['number']}/", {'email': 'customer@example.com'}
        )
        self.assertEqual(email_only_response.status_code, 404)

        payment_response = self.client.post(
            f"/api/ecommerce/orders/{order['number']}/payments/",
            {
                'tracking_token': order['tracking_token'], 'method': 'bkash',
                'transaction_id': 'TEST-TXN', 'amount': '1.00',
            },
            format='json',
        )
        self.assertEqual(payment_response.status_code, 201)
        self.assertEqual(payment_response.json()['amount'], '2480.00')
        self.assertEqual(Order.objects.using('ecommerce').count(), 1)
        self.variant.refresh_from_db(using='ecommerce')
        self.assertEqual(self.variant.stock, 3)

    def test_free_shipping_threshold_is_applied(self):
        self.variant.price = '3100.00'
        self.variant.save(using='ecommerce', update_fields=['price'])
        cart = self.client.post('/api/ecommerce/cart/', {
            'variant_id': self.variant.pk, 'quantity': 1,
        }, format='json').json()
        response = self.client.post('/api/ecommerce/checkout/', {
            'cart_token': cart['token'], 'customer_name': 'Test Customer',
            'email': 'customer@example.com', 'phone': '01700000000',
            'shipping_address': {'address': 'Test Road', 'city': 'Dhaka'},
            'shipping_total': '999999.00',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['shipping_total'], '0.00')

