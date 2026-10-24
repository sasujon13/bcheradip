from decimal import Decimal
from io import StringIO
from tempfile import TemporaryDirectory
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings
from .test_checkout_hardening import CheckoutHardeningTests as Fixtures
from .models import Product, ProductVariant, Order, OrderItem, Payment, DeliverySettings
from .order_reporting import order_contribution
from .order_service import change_order
from .checkout_rules import quote_totals
from .supplier_delivery import validate_rates


class ReportingAndDeliveryTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}
    setUp = Fixtures.setUp
    cart = Fixtures.cart
    payload = Fixtures.payload

    def order(self, **kwargs):
        return Order.objects.using('ecommerce').create(customer_name='Test', email='test@example.com', phone='01710000000',
            payment_status='paid', status='completed', grand_total=1000, **kwargs)

    def test_refund_negates_paid_value_and_preserves_incurred_costs(self):
        order = self.order(cost_snapshot={'items': [{'source':'Supplier A','quantity':1,'unit_source_cost':'500'}], 'supplier_delivery':'80'})
        report = order_contribution(Order.objects.using('ecommerce'))
        self.assertEqual(report['net'], Decimal('420'))
        change_order(order.pk, 'returned')
        change_order(order.pk, 'refunded')
        order.refresh_from_db(using='ecommerce')
        self.assertEqual(order.payment_status, 'refunded')
        report = order_contribution(Order.objects.using('ecommerce'))
        self.assertEqual(report['refunds'], 1000)
        self.assertEqual(report['net'], -580)  # Costs are not magically recovered on customer refund.
        self.assertEqual(report['sources'][0]['source'], 'Supplier A')

    def test_legacy_refunded_paid_order_and_unknown_costs_never_inflate_net(self):
        self.order()
        order = self.order()
        Order.objects.using('ecommerce').filter(pk=order.pk).update(status='refunded')
        report = order_contribution(Order.objects.using('ecommerce'))
        self.assertEqual(report['gross'] - report['refunds'], 1000)
        self.assertEqual(report['net'], 0)
        self.assertEqual(report['unresolved_orders'], 2)

    def test_supplier_direct_tariff_weight_quantity_and_cod(self):
        self.product.supplier_delivery_rates = {'dhaka':[{'up_to_grams':500,'charge':'65'},{'up_to_grams':1000,'charge':'90'}], 'outside':[{'up_to_grams':1000,'charge':'145'}]}
        self.variant.product = self.product
        self.variant.weight_grams = 400
        for district, quantity, expected in [('Dhaka',1,65), ('Dhaka',2,90), ('Dinajpur',2,145)]:
            totals, _ = quote_totals(1000*quantity, True, {'district':district}, lines=[(self.variant,quantity)])
            self.assertEqual(totals['shipping_total'], expected)
            self.assertEqual(totals['cod_total'], 10*quantity)
            self.assertEqual(Decimal(totals['delivery_details']['supplier_cost']), expected)
        for bad in [{'dhaka':[{'up_to_grams':True,'charge':50}]},{'dhaka':[{'up_to_grams':1000,'charge':-1}]},{'city':[]}]:
            with self.assertRaises(ValueError): validate_rates(bad)

    def test_supplier_tariffs_do_not_silently_consolidate_different_parcels(self):
        self.product.supplier_delivery_rates = {'dhaka':[{'up_to_grams':1000,'charge':'65'}]}
        self.variant.product = self.product; self.variant.weight_grams = 400
        second = Product.objects.using('ecommerce').create(name='Second', slug='second', category=self.category, supplier_delivery_rates=self.product.supplier_delivery_rates)
        v = ProductVariant(product=second, price=100, weight_grams=400, requires_shipping=True)
        totals,_ = quote_totals(1100, True, {'district':'Dhaka'}, lines=[(self.variant,1),(v,1)])
        self.assertEqual(totals['shipping_total'],130)
        self.product.supplier_delivery_rates = {**self.product.supplier_delivery_rates, 'shipment_group':'confirmed same parcel'}
        second.supplier_delivery_rates = self.product.supplier_delivery_rates
        totals,_ = quote_totals(1100, True, {'district':'Dhaka'}, lines=[(self.variant,1),(v,1)])
        self.assertEqual(totals['shipping_total'],65)

    def test_checkout_captures_costs_privately_and_does_not_reprice_history(self):
        self.product.supplier_delivery_rates = {'dhaka':[{'up_to_grams':1000,'charge':'65'}]}
        self.product.save(using='ecommerce')
        self.variant.weight_grams = 400; self.variant.save(using='ecommerce')
        response = self.client.post('/api/ecommerce/checkout/', self.payload(self.cart()), format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.assertNotIn('cost_snapshot', response.data)
        order = Order.objects.using('ecommerce').get(number=response.data['number'])
        self.assertEqual(order.cost_snapshot['items'][0]['unit_source_cost'],'400.00')
        self.assertEqual(Decimal(order.cost_snapshot['supplier_delivery']),65)
        self.variant.cost_price = 900; self.variant.save(using='ecommerce')
        order.refresh_from_db(using='ecommerce')
        self.assertEqual(order.cost_snapshot['items'][0]['unit_source_cost'],'400.00')

    def test_delete_api_protects_order_history_and_requires_delete_permission(self):
        self.user.is_staff=True; self.user.is_superuser=True; self.user.save()
        order=self.order()
        OrderItem.objects.using('ecommerce').create(order=order,product_id=self.product.pk,variant_id=self.variant.pk,product_name='Test',sku=self.variant.sku,quantity=1,unit_price=1000,line_total=1000)
        response=self.client.delete(f'/api/ecommerce/admin/products/{self.product.pk}/')
        self.assertEqual(response.status_code,400)
        order.delete(using='ecommerce')
        self.assertEqual(self.client.delete(f'/api/ecommerce/admin/products/{self.product.pk}/').status_code,204)

    def test_test_cleanup_refuses_real_payments_and_backs_up_scoped_samples(self):
        order=self.order()
        self.variant.sku='SAMPLE-TEST'; self.variant.save(using='ecommerce')
        OrderItem.objects.using('ecommerce').create(order=order,product_id=self.product.pk,variant_id=self.variant.pk,product_name='Test',sku=self.variant.sku,quantity=1,unit_price=1000,line_total=1000)
        payment=Payment.objects.using('ecommerce').create(order=order,method='cod',amount=1000,status='confirmed')
        with self.assertRaises(CommandError):
            call_command('remove_test_commerce',product_id=self.product.pk,order_id=order.pk,confirm_test_data=True,stdout=StringIO())
        payment.delete(using='ecommerce')
        with TemporaryDirectory() as directory, override_settings(BASE_DIR=directory):
            call_command('remove_test_commerce',product_id=self.product.pk,order_id=order.pk,confirm_test_data=True,stdout=StringIO())
            from pathlib import Path
            self.assertEqual(len(list(Path(directory).rglob('*.json'))),1)
        self.assertFalse(Product.objects.using('ecommerce').filter(pk=self.product.pk).exists())
        self.assertFalse(Order.objects.using('ecommerce').filter(pk=order.pk).exists())

    def test_default_subsidy_off_and_owner_ads_allowance(self):
        policy=DeliverySettings.current()
        self.assertFalse(policy.delivery_subsidy_enabled)
        self.assertEqual(policy.cost_defaults['ads_cost'],'20.00')
