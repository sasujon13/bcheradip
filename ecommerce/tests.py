import csv
import io
import tempfile

from django.test import SimpleTestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .csv_import import CSV_COLUMNS, sample_csv_text
from .db_router import EcommerceRouter
from .book_builder import build_book_asset
from .book_catalog import sync_book_catalog
from .models import Book, BookAsset, BookBuildJob, Category, Order, Product, ProductVariant


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


class BookStorefrontTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}
    reset_sequences = True

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_FORWARDED_PROTO='https')
        self.book = Book.objects.using('ecommerce').create(
            title='Physics Test Paper', title_bn='পদার্থবিজ্ঞান টেস্ট পেপার',
            book_type='test_paper', audience='student', status='published',
            digital_price='120.00', hard_copy_available=True,
            hard_copy_price='350.00', hard_copy_quantity=8,
            source_type='question_sets',
            source_config={'questions': [{'question': 'বল কাকে বলে?', 'answer': 'ভরবেগের পরিবর্তনের হার।'}]},
        )
        sync_book_catalog(self.book, notify=False)

    def test_published_book_is_searchable_and_has_purchase_variants(self):
        response = self.client.get('/api/ecommerce/books/', {'audience': 'student', 'search': 'Physics'})
        self.assertEqual(response.status_code, 200)
        books = response.json().get('results', response.json())
        self.assertEqual(len(books), 1)
        self.assertIsNotNone(books[0]['digital_variant_id'])
        self.assertIsNotNone(books[0]['hard_copy_variant_id'])

    def test_copy_type_filters_hard_soft_and_both_books(self):
        soft_book = Book.objects.using('ecommerce').create(
            title='Digital Grammar Guide', book_type='grammar', audience='student',
            status='published', digital_price='80.00', hard_copy_available=False,
        )
        sync_book_catalog(soft_book, notify=False)

        hard_books = self.client.get('/api/ecommerce/books/', {'copy_type': 'hard'}).json()
        hard_books = hard_books.get('results', hard_books)
        self.assertEqual([book['id'] for book in hard_books], [self.book.id])

        soft_books = self.client.get('/api/ecommerce/books/', {'copy_type': 'soft'}).json()
        soft_books = soft_books.get('results', soft_books)
        self.assertCountEqual([book['id'] for book in soft_books], [self.book.id, soft_book.id])

        both_books = self.client.get('/api/ecommerce/books/', {'copy_type': 'both'}).json()
        both_books = both_books.get('results', both_books)
        self.assertEqual([book['id'] for book in both_books], [self.book.id])

    def test_paid_ebook_file_is_not_exposed_by_public_catalog(self):
        BookAsset.objects.using('ecommerce').create(
            book=self.book, title='Full book', asset_type='ebook', file_format='pdf',
            external_url='https://example.com/private-book.pdf',
        )
        BookAsset.objects.using('ecommerce').create(
            book=self.book, title='Sample', asset_type='sample', file_format='pdf',
            external_url='https://example.com/sample.pdf',
        )
        response = self.client.get(f'/api/ecommerce/books/{self.book.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([asset['title'] for asset in response.json()['assets']], ['Sample'])
        self.assertEqual(response.json()['available_formats'], ['pdf'])

    def test_book_builder_creates_html_asset(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            job = BookBuildJob.objects.using('ecommerce').create(
                book=self.book, output_format='html', source_config=self.book.source_config,
            )
            asset = build_book_asset(job)
            job.refresh_from_db(using='ecommerce')
            self.assertEqual(job.status, 'completed')
            self.assertEqual(asset.file_format, 'html')
            self.assertTrue(asset.file.name.endswith('.html'))

    def test_paid_order_unlocks_secure_digital_library(self):
        BookAsset.objects.using('ecommerce').create(
            book=self.book, title='Full book', asset_type='ebook', file_format='pdf',
            external_url='https://example.com/private-book.pdf', is_primary=True,
        )
        variant = ProductVariant.objects.using('ecommerce').get(sku=f'BOOK-{self.book.pk:06d}-DIGITAL')
        cart = self.client.post('/api/ecommerce/cart/', {'variant_id': variant.pk, 'quantity': 1}, format='json').json()
        checkout = self.client.post('/api/ecommerce/checkout/', {
            'cart_token': cart['token'], 'customer_name': 'Reader', 'email': 'reader@example.com',
            'phone': '01700000000', 'shipping_address': {'address': 'Dhaka'},
        }, format='json').json()
        denied = self.client.get('/api/ecommerce/digital-library/', {
            'order_number': checkout['number'], 'tracking_token': checkout['tracking_token'],
        })
        self.assertEqual(denied.status_code, 403)
        Order.objects.using('ecommerce').filter(number=checkout['number']).update(payment_status='paid')
        allowed = self.client.get('/api/ecommerce/digital-library/', {
            'order_number': checkout['number'], 'tracking_token': checkout['tracking_token'],
        })
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()[0]['slug'], self.book.slug)

