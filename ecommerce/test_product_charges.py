from decimal import Decimal
from django.test import TransactionTestCase
from . import test_checkout_hardening as fixtures
from .models import DeliverySettings, Order, Product, ProductVariant, Coupon


class ProductChargeTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}
    setUp = fixtures.CheckoutHardeningTests.setUp
    cart = fixtures.CheckoutHardeningTests.cart
    payload = fixtures.CheckoutHardeningTests.payload
    csv_file = fixtures.CheckoutHardeningTests.csv_file

    def quote(self, data):
        response = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def second_product(self, delivery=None, cod=None, price=2000):
        p = Product.objects.using('ecommerce').create(name='Second', slug='second', status='active', category=self.category,
            delivery_dhaka_charge=delivery, delivery_outside_dhaka_charge=delivery, cod_percent=cod)
        return ProductVariant.objects.using('ecommerce').create(product=p, sku='SECOND', price=price, stock=20, requires_shipping=True)

    def test_default_cod_is_one_percent_and_never_applies_to_wallet_or_prepaid(self):
        data = self.payload(self.cart())
        for method, fee in [('cod', 10), ('wallet', 0), ('bkash', 0), ('bank', 0)]:
            data['payment_method'] = method
            quote = self.quote(data)
            self.assertEqual(Decimal(quote['cod_total']), fee)
            self.assertEqual(Decimal(quote['grand_total']), Decimal('1080') + fee)

    def test_custom_delivery_and_cod_override_defaults_per_product(self):
        self.product.delivery_dhaka_charge = 50; self.product.delivery_outside_dhaka_charge = 175; self.product.cod_percent = Decimal('2.5')
        self.product.save(using='ecommerce')
        data = self.payload(self.cart())
        quote = self.quote(data)
        self.assertEqual(Decimal(quote['shipping_total']), 50)
        self.assertEqual(Decimal(quote['cod_total']), 25)
        data['shipping_address']['district'] = 'Cumilla'
        self.assertEqual(Decimal(self.quote(data)['shipping_total']), 175)

    def test_mixed_cart_delivery_uses_median_once_even_for_multiple_quantities(self):
        v = self.second_product(delivery=150)
        cart = self.cart()
        self.client.post(f"/api/ecommerce/cart/{cart['token']}/", {'variant_id': v.pk, 'quantity': 3}, format='json')
        quote = self.quote(self.payload(cart))
        self.assertEqual(Decimal(quote['shipping_total']), 115)
        self.assertEqual(Decimal(quote['cod_total']), 70)
        self.assertEqual(Decimal(quote['grand_total']), 7185)

    def test_discount_is_prorated_before_different_product_cod_rates(self):
        self.product.cod_percent = 2; self.product.save(using='ecommerce')
        v = self.second_product(delivery=150)
        cart = self.cart()
        self.client.post(f"/api/ecommerce/cart/{cart['token']}/", {'variant_id': v.pk, 'quantity': 1}, format='json')
        Coupon.objects.using('ecommerce').create(code='TEN', discount_type='percent', value=10)
        data = self.payload(cart); data['coupon_code'] = 'TEN'
        quote = self.quote(data)
        self.assertEqual(Decimal(quote['discount_total']), 300)
        self.assertEqual(Decimal(quote['cod_total']), 36)  # 900*2% + 1800*1%, excludes delivery
        self.assertEqual(Decimal(quote['grand_total']), 2851)

    def test_zero_waives_charges_while_null_restores_inheritance(self):
        self.product.delivery_dhaka_charge = 0; self.product.cod_percent = 0; self.product.save(using='ecommerce')
        data = self.payload(self.cart())
        quote = self.quote(data)
        self.assertEqual(Decimal(quote['shipping_total']), 0); self.assertEqual(Decimal(quote['cod_total']), 0)
        self.product.delivery_dhaka_charge = None; self.product.cod_percent = None; self.product.save(using='ecommerce')
        quote = self.quote(data)
        self.assertEqual(Decimal(quote['shipping_total']), 80); self.assertEqual(Decimal(quote['cod_total']), 10)

    def test_central_changes_only_affect_inheriting_products_and_never_reprice_old_orders(self):
        data = self.payload(self.cart())
        first = self.client.post('/api/ecommerce/checkout/', data, format='json').json()
        DeliverySettings.objects.using('ecommerce').create(dhaka_charge=95, outside_dhaka_charge=130, cod_percent=3)
        new_quote = self.quote(self.payload(self.cart()))
        self.assertEqual(Decimal(new_quote['shipping_total']), 95); self.assertEqual(Decimal(new_quote['cod_total']), 30)
        self.product.cod_percent = 0; self.product.delivery_dhaka_charge = 40; self.product.save(using='ecommerce')
        custom_quote = self.quote(self.payload(self.cart()))
        self.assertEqual(Decimal(custom_quote['shipping_total']), 40); self.assertEqual(Decimal(custom_quote['cod_total']), 0)
        old = Order.objects.using('ecommerce').get(number=first['number'])
        self.assertEqual(old.shipping_total, 80); self.assertEqual(old.cod_total, 10); self.assertEqual(old.grand_total, 1090)

    def test_changed_override_blocks_old_quote_without_creating_order(self):
        data = self.payload(self.cart()); data['quoted_total'] = str(self.quote(data)['grand_total'])
        self.product.cod_percent = 4; self.product.save(using='ecommerce')
        response = self.client.post('/api/ecommerce/checkout/', data, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Decimal(response.data['cod_total']), 40)
        self.assertEqual(Order.objects.using('ecommerce').count(), 0)

    def test_product_and_central_fee_validation_rejects_negative_or_over_100_percent(self):
        self.user.is_staff = self.user.is_superuser = True; self.user.save()
        for field, value in [('delivery_dhaka_charge', -1), ('delivery_outside_dhaka_charge', -1), ('cod_percent', 101), ('cod_percent', 'NaN')]:
            response = self.client.patch(f'/api/ecommerce/admin/products/{self.product.pk}/', {field: value}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch('/api/ecommerce/admin/delivery-settings/', {'cod_percent': -1}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f'/api/ecommerce/admin/products/{self.product.pk}/', {'cod_percent': 0, 'delivery_dhaka_charge': 0}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.patch(f'/api/ecommerce/admin/products/{self.product.pk}/', {'cod_percent': None, 'delivery_dhaka_charge': None}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def test_shipping_coupon_waives_median_delivery_but_does_not_discount_cod_base(self):
        Coupon.objects.using('ecommerce').create(code='SHIP', discount_type='shipping', value=0)
        data = self.payload(self.cart()); data['coupon_code'] = 'SHIP'
        quote = self.quote(data)
        self.assertEqual(Decimal(quote['shipping_total']), 0); self.assertEqual(Decimal(quote['cod_total']), 10)

    def test_cod_rounding_is_half_up_and_does_not_include_courier(self):
        self.variant.price = Decimal('0.50'); self.variant.save(using='ecommerce')
        quote = self.quote(self.payload(self.cart()))
        self.assertEqual(Decimal(quote['cod_total']), Decimal('0.01'))
        self.assertEqual(Decimal(quote['grand_total']), Decimal('80.51'))

    def test_csv_can_set_preserve_and_reset_product_charge_overrides(self):
        self.user.is_staff = self.user.is_superuser = True; self.user.save()
        row = {'Handle': self.product.slug, 'Title': 'Product', 'Product Category': 'General', 'SKU': self.variant.sku,
               'Price': '1000', 'Dhaka Delivery Charge': '45', 'Outside Dhaka Delivery Charge': '200', 'COD Percent': '0'}
        for updates, expected in [({}, (Decimal('45'), Decimal('200'), Decimal('0'))),
                                  ({'Dhaka Delivery Charge': '', 'COD Percent': ''}, (Decimal('45'), Decimal('200'), Decimal('0'))),
                                  ({'Dhaka Delivery Charge': 'DEFAULT', 'COD Percent': 'DEFAULT'}, (None, Decimal('200'), None))]:
            row.update(updates)
            response = self.client.post('/api/ecommerce/admin/import/products/', {'file': self.csv_file(row)})
            self.assertEqual(response.data['failed'], 0, response.data)
            self.product.refresh_from_db(using='ecommerce')
            self.assertEqual((self.product.delivery_dhaka_charge, self.product.delivery_outside_dhaka_charge, self.product.cod_percent), expected)

    def test_quote_rejects_unknown_payment_method(self):
        data = self.payload(self.cart()); data['payment_method'] = 'unknown'
        response = self.client.post('/api/ecommerce/checkout/quote/', data, format='json')
        self.assertEqual(response.status_code, 400)
