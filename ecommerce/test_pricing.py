from decimal import Decimal
from unittest.mock import patch
from django.test import SimpleTestCase, TransactionTestCase
from . import test_checkout_hardening as fixtures
from .pricing import calculate_price, normalize_costs
from .models import Product, ProductVariant, Order, DeliverySettings
from .checkout_rules import quote_totals
from .admin_forms import ProductVariantAdminForm


class PricingMathTests(SimpleTestCase):
    def test_all_whole_cost_tiers_and_boundaries(self):
        for cost, rate in [('0','20'),('10','20'),('99.99','20'),('100','20'),('100.01','19'),
                           ('200','19'),('200.01','18'),('300','18'),('400','17'),('500','16'),
                           ('600','15'),('700','14'),('800','13'),('900','12'),('999.99','11'),
                           ('1000','11'),('1000.01','10'),('1100','10'),('1000000','10')]:
            self.assertEqual(Decimal(calculate_price(cost, {})['markup_percent']), Decimal(rate))

    def test_subsidy_and_all_costs_are_marked_up_not_just_source_price(self):
        result = calculate_price(500, {'supplier_delivery_max': 150, 'customer_delivery_charge': 80,
            'ads_cost': 30, 'packaging_cost': 10, 'returns_allowance': 20, 'other_costs': 10})
        self.assertEqual(result['total_cost'], '640.00')
        self.assertEqual(result['delivery_subsidy'], '70.00')
        self.assertEqual(result['markup_percent'], '14')
        self.assertEqual(result['profit_amount'], '89.60')
        self.assertEqual(result['suggested_price'], '729.60')

    def test_subsidy_never_negative_and_half_up_rounding(self):
        self.assertEqual(calculate_price('0.05', {'customer_delivery_charge': 80})['suggested_price'], '0.06')
        self.assertEqual(calculate_price(100, {'supplier_delivery_max': 50, 'customer_delivery_charge': 80})['delivery_subsidy'], '0.00')

    def test_rejects_invalid_inputs_and_overflow(self):
        for invalid in [-1, 'NaN', 'Infinity', True, '1.001', None, 'invalid']:
            with self.assertRaises(ValueError): calculate_price(invalid, {})
            with self.assertRaises(ValueError): normalize_costs({'ads_cost': invalid})
        for costs in [[], '', {'unknown': 2}]:
            with self.assertRaises(ValueError): normalize_costs(costs)
        with self.assertRaises(ValueError): calculate_price('999999999999.99', {})

    def test_median_deduplicates_variants_and_ignores_quantities_and_digital_lines(self):
        products = [Product(pk=n, delivery_dhaka_charge=fee) for n, fee in [(1,0),(2,80),(3,200)]]
        variants = [ProductVariant(product=p, price=Decimal('10'), requires_shipping=True) for p in products]
        digital = ProductVariant(product=Product(pk=4, delivery_dhaka_charge=900), price=Decimal('10'), requires_shipping=False)
        with patch('ecommerce.checkout_rules.DeliverySettings.current', return_value=DeliverySettings()):
            result, _ = quote_totals(Decimal('100'), True, {'district':'Dhaka'}, lines=[(variants[0],1),(variants[1],50),(variants[2],1),(variants[2],1),(digital,1)])
            self.assertEqual(result['shipping_total'], 100)
            even, _ = quote_totals(20, True, {'district':'Dhaka'}, lines=[(variants[0],1),(variants[1],1)])
            self.assertEqual(even['shipping_total'], 40)
            digital_only, _ = quote_totals(10, False, {}, lines=[(digital,1)])
            self.assertEqual(digital_only['shipping_total'], 0)


class PricingIntegrationTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}
    setUp = fixtures.CheckoutHardeningTests.setUp
    csv_file = fixtures.CheckoutHardeningTests.csv_file
    grant = fixtures.CheckoutHardeningTests.grant

    def staff(self):
        self.user.is_staff = True; self.user.is_superuser = True; self.user.save()

    def test_preview_is_private_read_only_and_does_not_change_prices(self):
        body = {'source_cost': 500, 'costs': {'ads_cost': 100}}
        self.assertIn(self.guest.post('/api/ecommerce/admin/pricing/preview/', body, format='json').status_code, (401,403))
        self.assertIn(self.client.post('/api/ecommerce/admin/pricing/preview/', body, format='json').status_code, (401,403))
        self.staff()
        response = self.client.post('/api/ecommerce/admin/pricing/preview/', body, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['suggested_price'], '690.00')
        self.variant.refresh_from_db(using='ecommerce')
        self.assertEqual(self.variant.price, 1000)
        self.assertEqual(Order.objects.using('ecommerce').count(), 0)

    def test_invalid_preview_is_rejected(self):
        self.staff()
        for body in [{'source_cost': -1}, {'source_cost': 20, 'costs': {'ads_cost': 'NaN'}}, {'source_cost': 2, 'costs': []}]:
            self.assertEqual(self.client.post('/api/ecommerce/admin/pricing/preview/', body, format='json').status_code, 400)

    def test_private_inputs_save_but_are_not_in_public_details(self):
        self.staff()
        data = {'variants': [{'id':self.variant.pk, 'pricing_inputs':{'ads_cost': 20}}]}
        response = self.client.patch(f'/api/ecommerce/admin/products/{self.product.pk}/', data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.variant.refresh_from_db(using='ecommerce')
        self.assertEqual(self.variant.pricing_inputs['ads_cost'], '20.00')
        self.assertEqual(self.variant.price, 1000)
        public = self.guest.get('/api/ecommerce/products/product/').json()
        self.assertNotIn('pricing_inputs', public['variants'][0]); self.assertNotIn('cost_price', public['variants'][0])
        bad = self.client.patch(f'/api/ecommerce/admin/products/{self.product.pk}/', {'variants':[{'id':self.variant.pk,'pricing_inputs': []}]}, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_csv_applies_only_when_explicit_and_preserves_costs_on_other_updates(self):
        self.staff()
        row = {'Handle': self.product.slug, 'Title':'Product', 'SKU':self.variant.sku, 'Cost Per Item':'500', 'Ads Cost':'100'}
        for apply, price in [('',Decimal('1000')), ('TRUE',Decimal('690')), ('',Decimal('690'))]:
            row['Apply Calculated Price'] = apply
            response = self.client.post('/api/ecommerce/admin/import/products/', {'file': self.csv_file(row)})
            self.assertEqual(response.data['failed'], 0, response.data)
            self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.price, price)
        row['Cost Per Item']=''; row['Ads Cost']=''; row['Price']='700'
        response = self.client.post('/api/ecommerce/admin/import/products/', {'file': self.csv_file(row)})
        self.assertEqual(response.data['failed'], 0)
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.pricing_inputs['ads_cost'], '100.00')

    def test_new_csv_sku_can_calculate_without_a_manual_price(self):
        self.staff()
        row = {'Handle':'new-product', 'Title':'New Product','SKU':'NEW-CALC','Cost Per Item':'500',
            'Ads Cost':'100','Inventory Quantity':'2','Apply Calculated Price':'TRUE'}
        response = self.client.post('/api/ecommerce/admin/import/products/', {'file':self.csv_file(row)})
        self.assertEqual(response.data['failed'], 0, response.data)
        self.assertEqual(ProductVariant.objects.using('ecommerce').get(sku='NEW-CALC').price, Decimal('690'))

    def test_preview_is_available_to_view_only_variant_staff_without_write_access(self):
        self.user.is_staff=True; self.user.save(); self.grant(ProductVariant,'view')
        response=self.client.post('/api/ecommerce/admin/pricing/preview/', {'source_cost':100}, format='json')
        self.assertEqual(response.status_code,200,response.data)
        denied=self.client.patch(f'/api/ecommerce/admin/products/{self.product.pk}/', {'name':'Changed'}, format='json')
        self.assertIn(denied.status_code,(401,403))

    def test_median_quote_matches_checkout_and_stored_order(self):
        second=Product.objects.using('ecommerce').create(name='Second',slug='second',category=self.category,status='active',delivery_dhaka_charge=150)
        v=ProductVariant.objects.using('ecommerce').create(product=second,sku='SECOND',price=200,stock=4,requires_shipping=True)
        cart=fixtures.CheckoutHardeningTests.cart(self)
        self.client.post(f"/api/ecommerce/cart/{cart['token']}/", {'variant_id':v.pk,'quantity':2},format='json')
        data=fixtures.CheckoutHardeningTests.payload(self,cart)
        quote=self.client.post('/api/ecommerce/checkout/quote/',data,format='json')
        self.assertEqual(Decimal(quote.data['shipping_total']),115)
        data['quoted_total']=str(quote.data['grand_total'])
        order=self.client.post('/api/ecommerce/checkout/',data,format='json')
        self.assertEqual(order.status_code,201,order.data)
        self.assertEqual(Decimal(order.data['shipping_total']),115)
        self.assertEqual(Decimal(order.data['grand_total']),1529)

    def test_django_admin_form_keeps_manual_price_unless_apply_is_checked(self):
        for apply, expected in [(False, Decimal('1000')), (True, Decimal('690'))]:
            self.variant.refresh_from_db(using='ecommerce')
            data = {'product':self.product.pk,'title':'Blue','sku':self.variant.sku,'price':'1000','cost_price':'500',
                'stock':10,'currency':'BDT','low_stock_threshold':5,'weight_grams':0,'is_active':True,'requires_shipping':True,
                'ads_cost':100, 'apply_suggested_price':apply}
            if apply: data['price']=''
            form = ProductVariantAdminForm(data=data, instance=self.variant)
            self.assertTrue(form.is_valid(), form.errors)
            saved = form.save(); self.assertEqual(Decimal(saved.price), expected)
