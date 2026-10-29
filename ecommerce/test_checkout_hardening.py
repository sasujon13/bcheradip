import csv
import io
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from cheradip.models import Customer, CustomerToken
from .models import Cart, Category, DeliverySettings, Order, Payment, Product, ProductVariant, Review, Shipment
from .csv_import import CSV_COLUMNS


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CheckoutHardeningTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        cache.clear()
        self.user = Customer.objects.create_user(username='01710000000', password='test', fullName='Shared Customer',
            email='customer@example.com', district='Dhaka', division='Dhaka', thana='Savar', union='Zone 1', village='Road 1')
        CustomerToken.objects.create(customer=self.user, key='checkout-test-token')
        self.client = APIClient()
        self.client.credentials(HTTP_X_FORWARDED_PROTO='https', HTTP_AUTHORIZATION='Bearer checkout-test-token')
        self.guest = APIClient()
        self.guest.credentials(HTTP_X_FORWARDED_PROTO='https')
        self.category = Category.objects.using('ecommerce').create(name='General', slug='general')
        self.product = Product.objects.using('ecommerce').create(name='Product', slug='product', status='active', category=self.category)
        self.variant = ProductVariant.objects.using('ecommerce').create(product=self.product, sku='TEST-SKU', title='Blue',
            price=1000, stock=10, cost_price=400, requires_shipping=True)

    def grant(self, model, action):
        ct, _ = ContentType.objects.get_or_create(app_label='ecommerce', model=model._meta.model_name)
        perm, _ = Permission.objects.get_or_create(content_type=ct, codename=f'{action}_{model._meta.model_name}', defaults={'name': action})
        self.user.user_permissions.add(perm)

    def cart(self, client=None):
        return (client or self.client).post('/api/ecommerce/cart/', {'variant_id': self.variant.pk, 'quantity': 1}, format='json').json()

    def payload(self, cart, district='Dhaka'):
        return {'cart_token': cart['token'], 'customer_name': 'Customer', 'email': 'customer@example.com',
            'phone': '01710000000', 'phone_alternate': '01810000000',
            'shipping_address': {'country_code': 'BD', 'district': district, 'thana': 'Savar', 'address': 'Road 1'},
            'payment_method': 'cod'}

    def test_one_customer_profile_prefills_delivery_without_exposing_settings(self):
        data = self.client.get('/api/ecommerce/checkout/profile/').json()
        self.assertEqual(data['district'], 'Dhaka')
        self.assertEqual(data['zone'], 'Zone 1')
        self.assertEqual(data['phone'], self.user.username)
        self.assertNotIn('settings', data)
        self.assertIn(self.guest.get('/api/ecommerce/checkout/profile/').status_code, (401, 403))

    def test_browsing_empty_cart_does_not_create_records(self):
        for _ in range(3):
            self.assertEqual(self.guest.get('/api/ecommerce/cart/').json()['items'], [])
        self.assertEqual(Cart.objects.using('ecommerce').count(), 0)

    def test_public_details_hide_cost_and_inactive_variants(self):
        ProductVariant.objects.using('ecommerce').create(product=self.product, sku='HIDDEN', price=5, stock=1, is_active=False)
        detail = self.guest.get('/api/ecommerce/products/product/').json()
        self.assertEqual(len(detail['variants']), 1)
        self.assertNotIn('cost_price', detail['variants'][0])

    def test_default_variant_is_buyable(self):
        self.variant.stock = 0; self.variant.save(using='ecommerce')
        available = ProductVariant.objects.using('ecommerce').create(product=self.product, sku='AVAILABLE', price=20, stock=3)
        data = self.guest.get('/api/ecommerce/products/').json()['results'][0]
        self.assertEqual(data['default_variant_id'], available.pk)

    def test_quote_and_checkout_use_dhaka_district_charge(self):
        data = self.payload(self.cart())
        quote = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        self.assertEqual(quote.status_code, 200, quote.data)
        self.assertEqual(Decimal(quote.data['shipping_total']), 80)
        data['quoted_total'] = str(quote.data['grand_total'])
        order = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(order.status_code, 201, order.data)
        self.assertEqual(order.data['cod_total'], '10.00')
        self.assertEqual(order.data['grand_total'], '1090.00')
        self.assertEqual(order.data['shipping_address']['phone_alternate'], '01810000000')

    def test_outside_dhaka_and_bengali_dhaka_rates(self):
        for district, expected in [('Chattogram', 120), ('ঢাকা', 80), ('DHAKA', 80)]:
            data = self.payload(self.cart(), district)
            response = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
            self.assertEqual(Decimal(response.data['shipping_total']), expected)

    def test_admin_rate_edit_changes_quote_but_not_existing_order(self):
        first = self.client.post('/api/ecommerce/checkout/', self.payload(self.cart()), format='json').json()
        self.assertIn(self.client.patch('/api/ecommerce/admin/delivery-settings/', {'dhaka_charge': 95}, format='json').status_code, (401,403))
        self.user.is_staff = True; self.user.save()
        self.grant(DeliverySettings, 'change')
        edited = self.client.patch('/api/ecommerce/admin/delivery-settings/', {'dhaka_charge': 95}, format='json')
        self.assertEqual(edited.status_code, 200, edited.data)
        quote = self.client.post('/api/ecommerce/checkout/quote/', self.payload(self.cart()), format='json')
        self.assertEqual(Decimal(quote.data['shipping_total']), 95)
        self.assertEqual(Order.objects.using('ecommerce').get(number=first['number']).shipping_total, 80)

    def test_rate_change_requires_customer_to_review_new_total(self):
        data = self.payload(self.cart()); data['quoted_total'] = '1090'
        DeliverySettings.objects.using('ecommerce').create(dhaka_charge=95)
        response = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(response.status_code, 409)
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.stock, 10)
        self.assertEqual(Order.objects.using('ecommerce').count(), 0)

    def test_registered_mobile_coupon_is_one_percent_and_credits_referrer(self):
        referrer = Customer.objects.create_user(
            username='01820000000', password='test', fullName='Referrer', acctype='Student', settings={'balance': 0})
        data = self.payload(self.cart()); data['coupon_code'] = '01820000000'
        quote = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        self.assertEqual(quote.status_code, 200, quote.data)
        self.assertEqual(Decimal(quote.data['discount_total']), Decimal('10.00'))
        self.assertEqual(quote.data['coupon_kind'], 'referral')
        self.assertEqual(
            quote.data['referral_notice'],
            'Only a registered Cheradip mobile number is accepted. That account gets 1% of this subtotal; they can spend it on products or other Cheradip services, or withdraw it. Signup bonus ৳50 can be spent here but cannot be withdrawn.',
        )
        data['quoted_total'] = str(quote.data['grand_total'])
        order = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(order.status_code, 201, order.data)
        from cheradip.models import RewardsWallet, WalletOperation
        from .order_service import change_order
        from .referral_coupon import credit_key, hold_key, refund_key
        number = order.data['number']
        referrer.refresh_from_db()
        self.assertEqual(referrer.settings['balance'], 0)
        wallet = RewardsWallet.objects.get(customer=referrer)
        self.assertEqual(wallet.pending_taka, Decimal('10.00'))
        self.assertEqual(wallet.available_taka, Decimal('0.00'))
        self.assertTrue(WalletOperation.objects.filter(operation_key=hold_key(number)).exists())
        self.assertFalse(WalletOperation.objects.filter(operation_key=credit_key(number)).exists())

        placed = Order.objects.using('ecommerce').get(number=number)
        change_order(placed.pk, 'completed')
        change_order(placed.pk, 'completed')
        referrer.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(referrer.settings['balance'], 1000)
        self.assertEqual(wallet.pending_taka, Decimal('0.00'))
        self.assertEqual(wallet.available_taka, Decimal('10.00'))
        self.assertEqual(WalletOperation.objects.filter(operation_key=credit_key(number)).count(), 1)
        self.assertFalse(WalletOperation.objects.filter(operation_key=refund_key(number)).exists())

    def test_own_mobile_cannot_be_used_as_coupon(self):
        data = self.payload(self.cart()); data['coupon_code'] = '01710000000'
        response = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('coupon_code', response.data)

    def test_unregistered_mobile_cannot_be_used_as_coupon(self):
        data = self.payload(self.cart()); data['coupon_code'] = '01919919919'
        response = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('not registered', str(response.data['coupon_code']).lower())
        self.assertEqual(Order.objects.using('ecommerce').count(), 0)

    def test_cancelled_order_reverses_referral_coupon_credit(self):
        referrer = Customer.objects.create_user(
            username='01830000000', password='test', fullName='Referrer Two', acctype='Student', settings={'balance': 0})
        data = self.payload(self.cart()); data['coupon_code'] = '01830000000'
        quote = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        data['quoted_total'] = str(quote.data['grand_total'])
        placed = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(placed.status_code, 201, placed.data)
        from cheradip.models import RewardsWallet, WalletOperation
        from .order_service import change_order
        from .referral_coupon import credit_key, hold_key, refund_key
        number = placed.data['number']
        self.assertEqual(RewardsWallet.objects.get(customer=referrer).pending_taka, Decimal('10.00'))
        change_order(Order.objects.using('ecommerce').get(number=number).pk, 'cancelled')
        change_order(Order.objects.using('ecommerce').get(number=number).pk, 'cancelled')
        referrer.refresh_from_db()
        wallet = RewardsWallet.objects.get(customer=referrer)
        self.assertEqual(referrer.settings['balance'], 0)
        self.assertEqual(wallet.pending_taka, Decimal('0.00'))
        self.assertEqual(wallet.available_taka, Decimal('0.00'))
        self.assertTrue(WalletOperation.objects.filter(operation_key=hold_key(number)).exists())
        self.assertFalse(WalletOperation.objects.filter(operation_key=credit_key(number)).exists())
        self.assertEqual(WalletOperation.objects.filter(operation_key=refund_key(number)).count(), 1)

    def test_refund_after_complete_reverses_released_referral_coupon(self):
        referrer = Customer.objects.create_user(
            username='01840000000', password='test', fullName='Referrer Three', acctype='Student', settings={'balance': 0})
        data = self.payload(self.cart()); data['coupon_code'] = '01840000000'
        quote = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        data['quoted_total'] = str(quote.data['grand_total'])
        placed = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(placed.status_code, 201, placed.data)
        from cheradip.models import RewardsWallet
        from .order_service import change_order
        order_id = Order.objects.using('ecommerce').get(number=placed.data['number']).pk
        change_order(order_id, 'completed')
        referrer.refresh_from_db()
        self.assertEqual(referrer.settings['balance'], 1000)
        change_order(order_id, 'returned')
        change_order(order_id, 'refunded')
        referrer.refresh_from_db()
        wallet = RewardsWallet.objects.get(customer=referrer)
        self.assertEqual(referrer.settings['balance'], 0)
        self.assertEqual(wallet.pending_taka, Decimal('0.00'))
        self.assertEqual(wallet.available_taka, Decimal('0.00'))

    def test_invalid_coupon_does_not_silently_place_full_price_order(self):
        data = self.payload(self.cart()); data['coupon_code'] = 'MISSING'
        response = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('coupon_code', response.data)
        self.assertEqual(Order.objects.using('ecommerce').count(), 0)

    def test_checkout_validates_payment_and_contact_fields(self):
        for field, value in [('payment_method', 'invented'), ('phone', 'abc'), ('email', 'not-email'), ('shipping_address', 'wrong')]:
            data = self.payload(self.cart()); data[field] = value
            response = self.client.post('/api/ecommerce/checkout/', data, format='json')
            self.assertEqual(response.status_code, 400, response.data)

    def test_staff_without_order_permission_cannot_read_other_customers_orders(self):
        private = self.guest.post('/api/ecommerce/checkout/', self.payload(self.cart(self.guest)), format='json').json()
        Order.objects.using('ecommerce').filter(number=private['number']).update(admin_note='INTERNAL-SECRET')
        self.user.is_staff = True; self.user.save()
        listed = self.client.get('/api/ecommerce/orders/').json()
        self.assertEqual(listed.get('results', listed) if isinstance(listed, dict) else listed, [])
        self.assertEqual(self.client.get(f"/api/ecommerce/track/{private['number']}/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/ecommerce/orders/{private['number']}/payments/", {'method': 'bank'}, format='json').status_code, 403)

    def test_customer_response_hides_internal_order_and_payment_notes(self):
        order = self.client.post('/api/ecommerce/checkout/', self.payload(self.cart()), format='json').json()
        row = Order.objects.using('ecommerce').get(number=order['number'])
        row.admin_note = 'SECRET'; row.save(using='ecommerce')
        Payment.objects.using('ecommerce').create(order=row, method='bank', amount=1080, note='SECRET')
        data = self.client.get(f"/api/ecommerce/track/{row.number}/").json()
        self.assertNotIn('admin_note', data); self.assertNotIn('checkout_token', data)
        self.assertNotIn('note', data['payments'][0])

    def test_review_uses_shared_bearer_and_requires_completed_purchase(self):
        response = self.client.post(f'/api/ecommerce/products/{self.product.pk}/reviews/', {'rating': 5, 'body': 'Nice'}, format='json')
        self.assertEqual(response.status_code, 403)
        order = self.client.post('/api/ecommerce/checkout/', self.payload(self.cart()), format='json').json()
        Order.objects.using('ecommerce').filter(number=order['number']).update(status='completed', payment_status='paid')
        response = self.client.post(f'/api/ecommerce/products/{self.product.pk}/reviews/', {'rating': 5, 'body': 'Nice', 'customer_name': 'Spoofed'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['customer_name'], 'Shared Customer')
        self.assertFalse(response.data['is_approved'])
        self.assertEqual(self.client.post(f'/api/ecommerce/products/{self.product.pk}/reviews/', {'rating': 5}, format='json').status_code, 409)

    def test_non_wallet_payment_details_are_atomic_with_checkout(self):
        data = self.payload(self.cart()); data.update(payment_method='bkash', transaction_id='ABC12345')
        response = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        payment = Payment.objects.using('ecommerce').get(order__number=response.data['number'])
        self.assertEqual(payment.transaction_id, 'ABC12345'); self.assertEqual(payment.status, 'pending')

    def test_expired_unpaid_reservations_return_stock_only_once(self):
        order = self.client.post('/api/ecommerce/checkout/', self.payload(self.cart()), format='json').json()
        Order.objects.using('ecommerce').filter(number=order['number']).update(reservation_expires_at=timezone.now()-timedelta(hours=1))
        call_command('commerce_maintenance', stdout=io.StringIO())
        call_command('commerce_maintenance', stdout=io.StringIO())
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.stock, 10)
        self.assertEqual(Order.objects.using('ecommerce').get(number=order['number']).status, 'cancelled')
        self.assertEqual(len(mail.outbox), 1)

    def test_csv_cannot_move_sku_to_another_product(self):
        self.user.is_staff = self.user.is_superuser = True; self.user.save()
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS); writer.writeheader()
        writer.writerow({'Handle': 'another', 'Title': 'Another', 'Product Category': 'General', 'SKU': self.variant.sku, 'Price': '15', 'Inventory Quantity': '4'})
        response = self.client.post('/api/ecommerce/admin/import/products/', {'file': SimpleUploadedFile('test.csv', stream.getvalue().encode())})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['failed'], 1)
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.product_id, self.product.pk)

    def test_shipping_updates_validate_order_transition_and_sync_status(self):
        self.user.is_staff = self.user.is_superuser = True; self.user.save()
        order = self.client.post('/api/ecommerce/checkout/', self.payload(self.cart()), format='json').json()
        data = {'order': order['id'], 'carrier': 'Courier', 'status': 'shipped'}
        self.assertEqual(self.client.post('/api/ecommerce/admin/shipments/', data, format='json').status_code, 400)
        Order.objects.using('ecommerce').filter(pk=order['id']).update(status='confirmed')
        response = self.client.post('/api/ecommerce/admin/shipments/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.using('ecommerce').get(pk=order['id']).status, 'shipped')

    def csv_file(self, row):
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS); writer.writeheader(); writer.writerow(row)
        return SimpleUploadedFile('preview.csv', stream.getvalue().encode())

    def test_csv_preview_rolls_back_all_product_and_notification_writes(self):
        from .models import CommerceNotification, ImportJob
        self.user.is_staff = self.user.is_superuser = True; self.user.save()
        row = {'Handle': 'preview-product', 'Title': 'Preview', 'Product Category': 'General', 'SKU': 'PREVIEW', 'Price': '15', 'Inventory Quantity': '4'}
        response = self.client.post('/api/ecommerce/admin/import/products/', {'preview': 'true', 'file': self.csv_file(row)})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['preview']); self.assertEqual(response.data['created'], 1)
        self.assertFalse(Product.objects.using('ecommerce').filter(slug='preview-product').exists())
        self.assertEqual(ImportJob.objects.using('ecommerce').count(), 0)
        self.assertEqual(CommerceNotification.objects.using('ecommerce').count(), 0)

    def test_csv_stock_updates_require_expected_current_stock(self):
        self.user.is_staff = self.user.is_superuser = True; self.user.save()
        row = {'Handle': self.product.slug, 'Title': 'Product', 'Product Category': 'General', 'SKU': self.variant.sku, 'Price': '1000', 'Inventory Quantity': '8'}
        response = self.client.post('/api/ecommerce/admin/import/products/', {'file': self.csv_file(row)})
        self.assertEqual(response.data['failed'], 1)
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.stock, 10)
        row['Expected Inventory Quantity'] = '10'
        response = self.client.post('/api/ecommerce/admin/import/products/', {'file': self.csv_file(row)})
        self.assertEqual(response.data['failed'], 0, response.data)
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.stock, 8)

    def test_maintenance_never_mass_emails_historical_orders_or_cancels_submitted_payments(self):
        old = Order.objects.using('ecommerce').create(customer_name='Old', email='old@example.com', phone='01710000000')
        data = self.payload(self.cart()); data.update(payment_method='bank', transaction_id='BANK-123')
        order = self.client.post('/api/ecommerce/checkout/', data, format='json').json()
        Order.objects.using('ecommerce').filter(number=order['number']).update(reservation_expires_at=timezone.now()-timedelta(days=2))
        call_command('commerce_maintenance', stdout=io.StringIO())
        self.assertEqual(Order.objects.using('ecommerce').get(number=order['number']).status, 'pending')
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(old.number, mail.outbox[0].body)

    def test_updating_completed_shipment_metadata_does_not_reverse_order_status(self):
        self.user.is_staff = self.user.is_superuser = True; self.user.save()
        order = Order.objects.using('ecommerce').create(customer_name='Customer', email='customer@example.com', phone='01710000000', status='completed', payment_status='paid')
        shipment = Shipment.objects.using('ecommerce').create(order=order, status='delivered')
        response = self.client.patch(f'/api/ecommerce/admin/shipments/{shipment.pk}/', {'tracking_number': 'TRACK-123'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db(using='ecommerce'); self.assertEqual(order.status, 'completed')

    def test_django_bound_shipment_instance_still_advances_fulfilment(self):
        from .order_service import save_shipment
        order = Order.objects.using('ecommerce').create(customer_name='Customer', email='customer@example.com', phone='01710000000', status='confirmed')
        shipment = Shipment.objects.using('ecommerce').create(order=order, status='preparing')
        shipment.status = 'shipped'  # ModelForm binds new values before ModelAdmin.save_model
        save_shipment(shipment, {'status': 'shipped'}, self.user.pk)
        order.refresh_from_db(using='ecommerce'); self.assertEqual(order.status, 'shipped')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', SMTP_ENABLED=True,
        SMTP_HOST='smtp.example.com', SMTP_PORT=587, SMTP_USER='test-only', SMTP_PASSWORD='test-only',
        SMTP_FROM='Cheradip <no-reply@example.com>', SMTP_USE_TLS=True, SMTP_USE_SSL=False)
    def test_receipts_use_existing_transactional_smtp_configuration(self):
        self.client.post('/api/ecommerce/checkout/', self.payload(self.cart()), format='json')
        with patch('ecommerce.management.commands.commerce_maintenance.get_connection') as connection, patch('ecommerce.management.commands.commerce_maintenance.send_mail', return_value=1) as send:
            call_command('commerce_maintenance', stdout=io.StringIO())
        self.assertEqual(connection.call_args.kwargs['host'], 'smtp.example.com')
        self.assertTrue(connection.call_args.kwargs['use_tls'])
        self.assertEqual(send.call_args.args[2], 'Cheradip <no-reply@example.com>')

    def test_welcome_signup_bonus_in_main_wallet_pays_shop_checkout(self):
        from cheradip.models import RewardsWallet
        from cheradip.views import WELCOME_SIGNUP_BONUS_COINS
        self.user.settings = {'balance': WELCOME_SIGNUP_BONUS_COINS}
        self.user.save(update_fields=['settings'])
        RewardsWallet.objects.get_or_create(customer=self.user)
        bonus_product = Product.objects.using('ecommerce').create(
            name='Welcome Bonus Item', slug='welcome-bonus-item', status='active', category=self.category,
        )
        bonus_variant = ProductVariant.objects.using('ecommerce').create(
            product=bonus_product, sku='WELCOME-BONUS', title='Digital', price=50, stock=3,
            requires_shipping=False,
        )
        cart = self.client.post(
            '/api/ecommerce/cart/', {'variant_id': bonus_variant.pk, 'quantity': 1}, format='json',
        ).json()
        data = self.payload(cart)
        data['payment_method'] = 'wallet'
        response = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['payment_status'], 'paid')
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 0)
        wallet = RewardsWallet.objects.get(customer=self.user)
        self.assertEqual(float(wallet.available_taka), 0)
        self.assertEqual(float(wallet.pending_taka), 0)
