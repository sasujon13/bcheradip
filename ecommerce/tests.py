import csv
import io
import tempfile
from decimal import Decimal

from django.test import SimpleTestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from cheradip.models import Customer, CustomerToken, PackagePlan, PackageSubscription, RewardsWallet

from .csv_import import CSV_COLUMNS, sample_csv_text
from .db_router import EcommerceRouter
from .book_builder import build_book_asset
from .book_catalog import sync_book_catalog
from .models import Book, BookAsset, BookBuildJob, Cart, Category, Order, Payment, Product, ProductVariant
from .views import StorefrontProductPagination


class EcommerceConfigurationTests(SimpleTestCase):
    def test_storefront_batches_have_no_gaps_and_support_old_pages(self):
        factory = APIRequestFactory()
        catalog = list(range(65))
        for offset, limit in [(0, 24), (24, 12), (36, 12), (48, 12), (60, 12)]:
            paginator = StorefrontProductPagination()
            request = Request(factory.get('/api/ecommerce/products/', {'limit': limit, 'offset': offset}))
            self.assertEqual(paginator.paginate_queryset(catalog, request), catalog[offset:offset + limit])
            self.assertEqual(paginator.count, 65)
        paginator = StorefrontProductPagination()
        request = Request(factory.get('/api/ecommerce/products/', {'page': 2}))
        self.assertEqual(paginator.paginate_queryset(list(range(250)), request), list(range(100, 200)))

    def test_storefront_batch_size_is_bounded(self):
        paginator = StorefrontProductPagination()
        factory = APIRequestFactory()
        request = Request(factory.get('/api/ecommerce/products/', {'limit': 100000}))
        self.assertEqual(len(paginator.paginate_queryset(list(range(250)), request)), 100)

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
    databases = {'default', 'ecommerce'}
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
        self.assertEqual(order['cod_total'], '24.00')
        self.assertEqual(order['grand_total'], '2504.00')
        self.assertEqual(order['status'], 'pending')
        self.assertEqual(order['payment_status'], 'unpaid')

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
        self.assertEqual(payment_response.json()['amount'], '2504.00')
        placed_order = Order.objects.using('ecommerce').get(number=order['number'])
        self.assertEqual(placed_order.status, 'pending')
        self.assertEqual(placed_order.payment_status, 'pending')
        self.assertEqual(Order.objects.using('ecommerce').count(), 1)
        self.variant.refresh_from_db(using='ecommerce')
        self.assertEqual(self.variant.stock, 3)

    def test_dhaka_delivery_charge_applies_even_above_old_free_shipping_threshold(self):
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
        self.assertEqual(response.json()['shipping_total'], '80.00')


class WalletCommerceTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}
    reset_sequences = True

    def setUp(self):
        self.user = Customer.objects.create_user(
            username='01710000000', password='test-password', fullName='Wallet Customer',
            acctype='Others', settings={'balance': 50000},
        )
        self.token = CustomerToken.objects.create(key='wallet-commerce-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}', HTTP_X_FORWARDED_PROTO='https',
        )
        category = Category.objects.using('ecommerce').create(name='Digital', slug='digital')
        product = Product.objects.using('ecommerce').create(
            name='Digital Guide', slug='digital-guide', category=category, status='active',
        )
        self.variant = ProductVariant.objects.using('ecommerce').create(
            product=product, title='Soft copy', sku='DIGITAL-001', price='120.00', stock=5,
            requires_shipping=False,
        )

    def cart(self, client=None):
        client = client or self.client
        response = client.post('/api/ecommerce/cart/', {
            'variant_id': self.variant.pk, 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_cart_summary_restores_saved_items_without_creating_empty_carts(self):
        cart = self.cart()
        before = Cart.objects.using('ecommerce').count()
        for _ in range(2):
            summary = self.client.get('/api/ecommerce/cart/summary/').json()
            self.assertEqual(summary['token'], cart['token'])
            self.assertEqual(summary['count'], 1)
        self.assertEqual(Cart.objects.using('ecommerce').count(), before)
        restored = self.client.get('/api/ecommerce/cart/').json()
        self.assertEqual(restored['token'], cart['token'])
        self.assertEqual(Cart.objects.using('ecommerce').count(), before)

    def test_cart_summary_does_not_expose_a_customers_items_to_guests(self):
        cart = self.cart()
        guest = APIClient()
        guest.credentials(HTTP_X_FORWARDED_PROTO='https')
        before = Cart.objects.using('ecommerce').count()
        summary = guest.get('/api/ecommerce/cart/summary/', {'token': cart['token']}).json()
        self.assertEqual(summary, {'token': None, 'count': 0})
        self.assertEqual(Cart.objects.using('ecommerce').count(), before)

    def checkout_payload(self, token):
        return {
            'cart_token': token, 'customer_name': 'Wallet Customer',
            'email': 'wallet@example.com', 'phone': '01710000000',
            'shipping_address': {'address': 'Digital delivery', 'city': 'Dhaka'},
            'payment_method': 'wallet',
        }

    def test_wallet_checkout_deducts_coins_and_confirms_payment(self):
        RewardsWallet.objects.create(
            customer=self.user, available_taka='50.00', lifetime_earned_taka='50.00',
        )
        response = self.client.post(
            '/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['payment_status'], 'paid')
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['walletBalanceTaka'], 380.0)
        self.assertEqual(response.data['referenceUsedTaka'], 50.0)
        self.assertEqual(response.data['referenceBalanceTaka'], 0.0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 38000)
        self.assertEqual(RewardsWallet.objects.get(customer=self.user).available_taka, 0)
        payment = Payment.objects.using('ecommerce').get(order_id=response.data['id'])
        self.assertEqual((payment.method, payment.status), ('wallet', 'confirmed'))
        self.assertIn('Reference balance used first: Tk 50.00', payment.note)

        tracking = self.client.get(f"/api/ecommerce/track/{response.data['number']}/")
        self.assertEqual(tracking.status_code, 200, tracking.data)
        self.assertEqual(tracking.data['kind'], 'commerce')
        self.assertEqual(tracking.data['status_label'], 'Pending')
        self.assertEqual(tracking.data['payment_status_label'], 'Paid')

    def test_reference_portion_is_spent_before_remaining_main_wallet_value(self):
        self.user.settings = {'balance': 171300}
        self.user.save(update_fields=['settings'])
        RewardsWallet.objects.create(
            customer=self.user, available_taka='500.00', lifetime_earned_taka='500.00',
        )
        self.variant.price = '800.00'
        self.variant.save(using='ecommerce', update_fields=['price'])

        response = self.client.post(
            '/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json',
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['walletBalanceTaka'], 913.0)
        self.assertEqual(response.data['referenceUsedTaka'], 500.0)
        self.assertEqual(response.data['referenceBalanceTaka'], 0.0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 91300)
        self.assertEqual(RewardsWallet.objects.get(customer=self.user).available_taka, 0)

    def test_admin_completion_changes_pending_order_to_order_completed(self):
        response = self.client.post(
            '/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'pending')
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])
        self.client.force_authenticate(user=self.user)

        completed = self.client.patch(
            f"/api/ecommerce/admin/orders/{response.data['number']}/",
            {'status': 'completed', 'note': 'Checked and fulfilled.'},
            format='json',
        )

        self.assertEqual(completed.status_code, 200, completed.data)
        self.assertEqual(completed.data['status'], 'completed')
        self.assertEqual(completed.data['payment_status'], 'paid')
        tracked = self.client.get(f"/api/ecommerce/track/{response.data['number']}/")
        self.assertEqual(tracked.data['status_label'], 'Order Completed')

    def test_wallet_checkout_requires_login_and_preserves_stock(self):
        guest = APIClient()
        guest.credentials(HTTP_X_FORWARDED_PROTO='https')
        response = guest.post(
            '/api/ecommerce/checkout/', self.checkout_payload(self.cart(guest)['token']), format='json',
        )
        self.assertEqual(response.status_code, 401)
        self.variant.refresh_from_db(using='ecommerce')
        self.assertEqual(self.variant.stock, 5)

    def test_repeated_checkout_is_idempotent(self):
        payload = self.checkout_payload(self.cart()['token'])
        first = self.client.post('/api/ecommerce/checkout/', payload, format='json')
        second = self.client.post('/api/ecommerce/checkout/', payload, format='json')
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data['number'], second.data['number'])
        self.assertEqual(Order.objects.using('ecommerce').count(), 1)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 38000)

    def test_cancel_refunds_once_and_cannot_reopen_or_restock_twice(self):
        RewardsWallet.objects.create(customer=self.user, available_taka='50.00')
        order = self.client.post('/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json').data
        self.user.is_staff = True; self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])
        self.client.force_authenticate(self.user)
        url = f'/api/ecommerce/admin/orders/{order["number"]}/'
        self.assertEqual(self.client.patch(url, {'status': 'cancelled'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'status': 'cancelled'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'status': 'confirmed'}, format='json').status_code, 409)
        self.user.refresh_from_db(); self.variant.refresh_from_db(using='ecommerce')
        self.assertEqual((self.user.settings['balance'], self.variant.stock), (50000, 5))
        self.assertEqual(RewardsWallet.objects.get(customer=self.user).available_taka, 50)

    def test_paid_order_rejects_customer_payment_resubmission(self):
        order = self.client.post('/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json').data
        response = self.client.post(f'/api/ecommerce/orders/{order["number"]}/payments/', {'method': 'bkash', 'status': 'confirmed'}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.using('ecommerce').get(pk=order['id']).payment_status, 'paid')

    def test_add_cart_increments_but_quantity_control_sets(self):
        token = self.cart()['token']
        url = f'/api/ecommerce/cart/{token}/'
        added = self.client.post(url, {'variant_id': self.variant.pk, 'quantity': 1}, format='json')
        self.assertEqual(added.data['items'][0]['quantity'], 2)
        updated = self.client.post(url, {'variant_id': self.variant.pk, 'quantity': 3, 'operation': 'set'}, format='json')
        self.assertEqual(updated.data['items'][0]['quantity'], 3)

    def test_insufficient_wallet_does_not_create_order_or_deduct(self):
        self.user.settings = {'balance': 1000}
        self.user.save(update_fields=['settings'])
        RewardsWallet.objects.create(
            customer=self.user, available_taka='5.00', lifetime_earned_taka='5.00',
        )
        response = self.client.post(
            '/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json',
        )
        self.assertEqual(response.status_code, 402)
        self.assertEqual(Order.objects.using('ecommerce').count(), 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 1000)
        self.assertEqual(RewardsWallet.objects.get(customer=self.user).available_taka, 5)

    def test_history_contains_packages_and_orders_but_not_small_coin_activity(self):
        plan = PackagePlan.objects.create(
            code='history-plan', name='Starter', duration_months=1, track='academic',
            audience='student', list_price='100.00', price='80.00',
        )
        PackageSubscription.objects.create(
            customer=self.user, plan=plan, status='active', plan_price='80.00',
            payable_amount='80.00',
        )
        self.client.post(
            '/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json',
        )
        response = self.client.get('/api/ecommerce/account/history/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['profile']['accountType'], 'Others')
        self.assertEqual(len(response.data['packages']), 1)
        self.assertEqual(len(response.data['orders']), 1)
        self.assertNotIn('coinDeductions', response.data)

    def test_history_requires_a_valid_bearer_session(self):
        guest = APIClient()
        guest.credentials(HTTP_X_FORWARDED_PROTO='https')
        response = guest.get('/api/ecommerce/account/history/')
        self.assertEqual(response.status_code, 401)

    def test_archived_product_cannot_be_checked_out_from_old_cart(self):
        token = self.cart()['token']
        self.variant.product.status = 'archived'
        self.variant.product.save(using='ecommerce', update_fields=['status'])
        response = self.client.post('/api/ecommerce/checkout/', self.checkout_payload(token), format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.using('ecommerce').count(), 0)

    def test_another_account_cannot_use_cart_or_replay_checkout(self):
        token = self.cart()['token']
        second = Customer.objects.create_user(
            username='01722222222', password='password', fullName='Second Buyer',
            acctype='Others', settings={'balance': 50000},
        )
        second_token = CustomerToken.objects.create(key='other-buyer-token', customer=second)
        other = APIClient()
        other.credentials(HTTP_AUTHORIZATION=f'Bearer {second_token.key}', HTTP_X_FORWARDED_PROTO='https')
        self.assertNotEqual(other.get(f'/api/ecommerce/cart/{token}/').data['token'], token)
        self.assertEqual(other.post('/api/ecommerce/checkout/', self.checkout_payload(token), format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/ecommerce/checkout/', self.checkout_payload(token), format='json').status_code, 201)
        self.assertEqual(other.post('/api/ecommerce/checkout/', self.checkout_payload(token), format='json').status_code, 403)

    def test_recovered_refund_cannot_complete_paid_order_again(self):
        from cheradip.models import WalletOperation
        from .order_service import change_order, refund_wallet
        response = self.client.post('/api/ecommerce/checkout/', self.checkout_payload(self.cart()['token']), format='json')
        order = Order.objects.using('ecommerce').get(number=response.data['number'])
        self.assertTrue(WalletOperation.objects.filter(operation_key=f'commerce:debit:{order.number}').exists())
        refund_wallet(order)  # Simulate a committed refund before the commerce acknowledgement.
        with self.assertRaisesRegex(ValueError, 'refunded'):
            change_order(order.pk, 'completed')
        order.refresh_from_db(using='ecommerce')
        self.assertNotEqual(order.status, 'completed')

    def test_invalid_price_filters_are_client_errors(self):
        for parameter in ('min_price=abc', 'max_price=NaN', 'min_price=-1', 'min_price=100&max_price=1'):
            response = self.client.get('/api/ecommerce/products/?' + parameter)
            self.assertEqual(response.status_code, 400, parameter)


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

    def test_metadata_edit_does_not_reset_sold_inventory(self):
        variant = ProductVariant.objects.using('ecommerce').get(sku=f'BOOK-{self.book.pk:06d}-HARDCOPY')
        variant.stock = 3; variant.save(using='ecommerce')
        self.book.title = 'Updated title'; self.book.save(using='ecommerce')
        sync_book_catalog(self.book, notify=False)
        variant.refresh_from_db(using='ecommerce')
        self.assertEqual(variant.stock, 3)
        response = self.client.get(f'/api/ecommerce/books/{self.book.slug}/')
        self.assertEqual(response.data['hard_copy_quantity'], 3)

    def test_hard_copy_does_not_grant_digital_download(self):
        from .models import OrderItem
        order = Order.objects.using('ecommerce').create(customer_name='Reader', email='reader@example.com', phone='01700000000', status='completed', payment_status='paid')
        OrderItem.objects.using('ecommerce').create(order=order, product_id=self.book.product_id, variant_id=1, product_name=self.book.title, sku=f'BOOK-{self.book.pk:06d}-HARDCOPY', quantity=1, unit_price=350, line_total=350)
        query = {'order_number': order.number, 'tracking_token': order.tracking_token}
        self.assertEqual(self.client.get('/api/ecommerce/digital-library/', query).data, [])
        self.assertEqual(self.client.get(f'/api/ecommerce/digital-library/{self.book.slug}/download/', query).status_code, 404)

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
        with tempfile.TemporaryDirectory() as media_root, tempfile.TemporaryDirectory() as private_root, override_settings(MEDIA_ROOT=media_root, PRIVATE_EBOOK_ROOT=private_root):
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
        still_pending = self.client.get('/api/ecommerce/digital-library/', {
            'order_number': checkout['number'], 'tracking_token': checkout['tracking_token'],
        })
        self.assertEqual(still_pending.status_code, 403)
        Order.objects.using('ecommerce').filter(number=checkout['number']).update(status='completed')
        allowed = self.client.get('/api/ecommerce/digital-library/', {
            'order_number': checkout['number'], 'tracking_token': checkout['tracking_token'],
        })
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()[0]['slug'], self.book.slug)

    def test_signed_in_buyer_can_reopen_completed_digital_library_without_tracking_token(self):
        from .models import OrderItem
        buyer = Customer.objects.create_user(username='01733333333', password='password', fullName='Reader', acctype='Others')
        token = CustomerToken.objects.create(key='digital-owner-token', customer=buyer)
        BookAsset.objects.using('ecommerce').create(
            book=self.book, title='Guide', asset_type='ebook', file_format='pdf',
            external_url='https://example.com/guide.pdf', is_downloadable=True,
        )
        variant = ProductVariant.objects.using('ecommerce').get(sku=f'BOOK-{self.book.pk:06d}-DIGITAL')
        order = Order.objects.using('ecommerce').create(
            customer_id=buyer.pk, customer_name='Reader', email='reader@example.com',
            phone='01733333333', status='completed', payment_status='paid',
        )
        OrderItem.objects.using('ecommerce').create(
            order=order, product_id=self.book.product_id, variant_id=variant.pk,
            product_name=self.book.title, sku=variant.sku, quantity=1, unit_price=120, line_total=120,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}', HTTP_X_FORWARDED_PROTO='https')
        response = self.client.get('/api/ecommerce/digital-library/', {'order_number': order.number})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['slug'], self.book.slug)


class CsvAuditTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def _csv(self, rows):
        from .csv_import import CSV_COLUMNS
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        output.seek(0)
        return output

    def test_blank_update_preserves_price_and_stock(self):
        from .csv_import import import_products
        category = Category.objects.using('ecommerce').create(name='Accessories', slug='accessories')
        product = Product.objects.using('ecommerce').create(name='Old', slug='audit-item', category=category)
        variant = ProductVariant.objects.using('ecommerce').create(product=product, sku='AUDIT-SKU', price='12.00', stock=4)
        job = import_products(self._csv([{'Handle': 'audit-item', 'Title': 'Updated', 'SKU': 'AUDIT-SKU'}]))
        variant.refresh_from_db(using='ecommerce')
        self.assertEqual(job.failed_count, 0)
        self.assertEqual((variant.price, variant.stock), (Decimal('12.00'), 4))

    def test_failed_row_does_not_report_a_created_product(self):
        from .csv_import import import_products
        job = import_products(self._csv([{'Handle': 'bad-item', 'Title': 'Bad', 'SKU': ''}]))
        self.assertEqual((job.created_count, job.failed_count, job.status), (0, 1, 'failed'))
        self.assertFalse(Product.objects.using('ecommerce').filter(slug='bad-item').exists())

    def test_negative_price_is_rejected(self):
        from .csv_import import import_products
        job = import_products(self._csv([{
            'Handle': 'negative-item', 'Title': 'Negative', 'SKU': 'NEG-1',
            'Price': '-10', 'Inventory Quantity': '3',
        }]))
        self.assertEqual(job.failed_count, 1)
        self.assertFalse(Product.objects.using('ecommerce').filter(slug='negative-item').exists())

