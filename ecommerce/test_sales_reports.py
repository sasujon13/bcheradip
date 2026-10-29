from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient
from django.test import TransactionTestCase
from cheradip.models import Customer, CustomerToken
from .models import Category, Order, OrderItem, Product, ProductVariant, Supplier, SupplierOffer
from .sales_reporting import DHAKA


class SalesReportsTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='sales-staff', password='test-only', fullName='Sales Staff')
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        CustomerToken.objects.create(key='sales-test-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer sales-test-token', HTTP_X_FORWARDED_PROTO='https')
        self.category = Category.objects.using('ecommerce').create(name='Sales', slug='sales-test')
        self.alpha = Supplier.objects.using('ecommerce').create(
            name='Alpha source', website='https://alpha.example', enabled=True,
            terms_confirmed=True, terms_note='Test recollection licence')
        self.beta = Supplier.objects.using('ecommerce').create(
            name='Beta source', website='https://beta.example', enabled=True,
            terms_confirmed=True, terms_note='Test recollection licence')
        self.shirt = Product.objects.using('ecommerce').create(
            name='Alpha shirt', slug='alpha-shirt-sales', category=self.category, status='active')
        self.hat = Product.objects.using('ecommerce').create(
            name='Beta hat', slug='beta-hat-sales', category=self.category, status='active')
        self.own = Product.objects.using('ecommerce').create(
            name='Own mug', slug='own-mug-sales', category=self.category, status='active')
        self.shirt_variant = ProductVariant.objects.using('ecommerce').create(
            product=self.shirt, sku='ALPHA-SHIRT', price=Decimal('500.00'), cost_price=Decimal('200.00'), stock=10)
        self.hat_variant = ProductVariant.objects.using('ecommerce').create(
            product=self.hat, sku='BETA-HAT', price=Decimal('300.00'), cost_price=Decimal('120.00'), stock=10)
        self.own_variant = ProductVariant.objects.using('ecommerce').create(
            product=self.own, sku='OWN-MUG', price=Decimal('150.00'), cost_price=Decimal('40.00'), stock=10)
        SupplierOffer.objects.using('ecommerce').create(
            supplier=self.alpha, external_id='S1', vendor_id='v1', url='https://alpha.example/s1',
            title='Alpha shirt', imported_product=self.shirt, state='ready')
        SupplierOffer.objects.using('ecommerce').create(
            supplier=self.beta, external_id='H1', vendor_id='v1', url='https://beta.example/h1',
            title='Beta hat', imported_product=self.hat, state='ready')
        self.paid_shirt = self._order(
            'CH-SALES-1', self.shirt, self.shirt_variant, qty=2, line=Decimal('1000.00'),
            source='Alpha source', supplier_id=self.alpha.pk, unit_cost='200.00', delivery='80')
        self._order(
            'CH-SALES-2', self.shirt, self.shirt_variant, qty=1, line=Decimal('500.00'),
            source='Alpha source', supplier_id=self.alpha.pk, unit_cost='200.00', delivery='40')
        self._order(
            'CH-SALES-3', self.hat, self.hat_variant, qty=1, line=Decimal('300.00'),
            source='Beta source', supplier_id=self.beta.pk, unit_cost='120.00', delivery='50')
        self._order(
            'CH-SALES-4', self.own, self.own_variant, qty=1, line=Decimal('150.00'),
            source='Own inventory', supplier_id=None, unit_cost='40.00', delivery='20')

    def _order(self, number, product, variant, qty, line, source, supplier_id, unit_cost, delivery,
               payment_status='paid', status='completed'):
        order = Order.objects.using('ecommerce').create(
            number=number, customer_name='Buyer', email='buyer@example.com', phone='01710000000',
            payment_status=payment_status, status=status, grand_total=line,
            cost_snapshot={'items': [{
                'product_id': product.pk, 'quantity': qty, 'source': source,
                'supplier_id': supplier_id, 'unit_source_cost': unit_cost,
            }], 'supplier_delivery': delivery})
        OrderItem.objects.using('ecommerce').create(
            order=order, product_id=product.pk, variant_id=variant.pk, product_name=product.name,
            variant_title=variant.title, sku=variant.sku, quantity=qty, unit_price=variant.price, line_total=line)
        return order

    def test_all_suppliers_sales_units_profit_and_repeat_skus(self):
        response = self.client.get('/api/ecommerce/admin/sales-reports/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['view'], 'suppliers')
        self.assertEqual(response.data['totals']['sales'], Decimal('1950.00'))
        self.assertEqual(response.data['totals']['units'], 5)
        self.assertEqual(response.data['totals']['profit'], Decimal('1190.00'))
        self.assertEqual(response.data['totals']['repeat_skus'], 1)
        alpha = next(row for row in response.data['rows'] if row['supplier_name'] == 'Alpha source')
        self.assertEqual(alpha['sales'], Decimal('1500.00'))
        self.assertEqual(alpha['units'], 3)
        self.assertEqual(alpha['profit'], Decimal('900.00'))
        self.assertEqual(alpha['repeat_skus'], 1)
        self.assertEqual(alpha['skus_sold'], 1)
        beta = next(row for row in response.data['rows'] if row['supplier_name'] == 'Beta source')
        self.assertEqual((beta['sales'], beta['units'], beta['profit'], beta['repeat_skus']),
                         (Decimal('300.00'), 1, Decimal('180.00'), 0))
        own = next(row for row in response.data['rows'] if row['supplier_name'] == 'Own inventory')
        self.assertEqual((own['sales'], own['profit']), (Decimal('150.00'), Decimal('110.00')))
        self.assertEqual(response.data['totals']['top_product'], 'Alpha shirt')

    def test_one_supplier_lists_products_and_times_sold(self):
        response = self.client.get('/api/ecommerce/admin/sales-reports/', {'supplier': self.alpha.pk})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['view'], 'products')
        self.assertEqual(response.data['selected_supplier'], self.alpha.pk)
        self.assertEqual(len(response.data['rows']), 1)
        shirt = response.data['rows'][0]
        self.assertEqual(shirt['sku'], 'ALPHA-SHIRT')
        self.assertEqual(shirt['units'], 3)
        self.assertEqual(shirt['sales'], Decimal('1500.00'))
        self.assertEqual(shirt['profit'], Decimal('900.00'))
        self.assertEqual(shirt['profit_per_unit'], Decimal('300.00'))
        self.assertEqual(shirt['order_count'], 2)
        self.assertEqual(response.data['extras']['repeat_winners'][0]['sku'], 'ALPHA-SHIRT')

    def test_refund_zeroes_net_sales_and_keeps_refund_total(self):
        self._order(
            'CH-SALES-REF', self.hat, self.hat_variant, qty=1, line=Decimal('300.00'),
            source='Beta source', supplier_id=self.beta.pk, unit_cost='120.00', delivery='50',
            payment_status='refunded', status='refunded')
        response = self.client.get('/api/ecommerce/admin/sales-reports/', {'supplier': self.beta.pk})
        hat = response.data['rows'][0]
        self.assertEqual(hat['sales'], Decimal('300.00'))
        self.assertEqual(hat['refunds'], Decimal('300.00'))
        self.assertEqual(hat['units'], 1)
        self.assertEqual(hat['refunded_units'], 1)
        self.assertEqual(hat['profit'], Decimal('180.00'))

    def test_missing_snapshot_cost_keeps_sales_and_marks_profit_na(self):
        order = Order.objects.using('ecommerce').create(
            number='CH-SALES-NA', customer_name='Buyer', email='buyer@example.com', phone='01710000000',
            payment_status='paid', status='completed', grand_total=Decimal('500.00'), cost_snapshot={})
        OrderItem.objects.using('ecommerce').create(
            order=order, product_id=self.shirt.pk, variant_id=self.shirt_variant.pk, product_name=self.shirt.name,
            variant_title='Default', sku='ALPHA-SHIRT', quantity=1, unit_price=Decimal('500.00'),
            line_total=Decimal('500.00'))
        response = self.client.get('/api/ecommerce/admin/sales-reports/', {'supplier': self.alpha.pk})
        shirt = response.data['rows'][0]
        self.assertEqual(shirt['sales'], Decimal('2000.00'))
        self.assertIsNone(shirt['profit'])
        self.assertGreater(shirt['cost_unknown_units'], 0)
        self.assertIsNone(response.data['totals']['profit'])

    def test_date_range_excludes_older_orders(self):
        old = timezone.now() - timedelta(days=120)
        Order.objects.using('ecommerce').filter(pk=self.paid_shirt.pk).update(created_at=old)
        today = timezone.now().astimezone(DHAKA).date()
        start = (today - timedelta(days=30)).isoformat()
        today = today.isoformat()
        response = self.client.get('/api/ecommerce/admin/sales-reports/', {'from': start, 'to': today})
        self.assertEqual(response.data['totals']['units'], 3)
        self.assertEqual(response.data['date_from'], start)

    def test_unknown_supplier_and_guest_are_rejected(self):
        self.assertEqual(self.client.get('/api/ecommerce/admin/sales-reports/', {'supplier': 999999}).status_code, 400)
        guest = APIClient()
        self.assertIn(guest.get('/api/ecommerce/admin/sales-reports/').status_code, (401, 403))
