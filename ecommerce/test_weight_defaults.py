from copy import deepcopy
from decimal import Decimal
from django.test import SimpleTestCase, TransactionTestCase
from . import test_checkout_hardening as fixtures
from .cost_defaults import initial_courier_profiles, initial_cost_defaults
from .delivery_rates import weight_range, normalize_profiles, delivery_zone, listing_defaults
from .models import DeliverySettings, ProductVariant, Order
from .admin_forms import ProductVariantAdminForm
from .pricing import calculate_price


class WeightMathTests(SimpleTestCase):
    def test_verified_bands_and_midpoints(self):
        policy=DeliverySettings()
        for grams,zone,low,high,middle in [(500,'dhaka',60,80,70),(501,'dhaka',70,80,75),
            (1000,'dhaka',70,80,75),(1001,'dhaka',90,110,100),(2001,'dhaka',105,105,105),
            (500,'outside',110,160,135),(1000,'outside',130,160,145),(2000,'outside',160,190,175),
            (2001,'outside',195,195,195),(500,'suburbs',80,100,90)]:
            data=weight_range(policy,grams,zone)
            self.assertEqual((Decimal(data['minimum']),Decimal(data['maximum']),Decimal(data['midpoint'])),(low,high,middle))

    def test_unsupported_weight_and_ambiguous_bulk_service_are_not_invented(self):
        with self.assertRaises(ValueError): weight_range(DeliverySettings(),20001,'dhaka')
        data=weight_range(DeliverySettings(),3000,'outside')
        self.assertEqual([r['name'] for r in data['rates']],['Pathao'])

    def test_region_mapping_and_defaults_are_explicit(self):
        self.assertEqual(delivery_zone({'district':'ঢাকা','thana':'সাভার'}),'suburbs')
        self.assertEqual(delivery_zone({'district':'Gazipur'}),'suburbs')
        self.assertEqual(delivery_zone({'district':'Dhaka','thana':'Dhanmondi'}),'dhaka')
        costs,estimated=listing_defaults(DeliverySettings(),0)
        self.assertTrue(estimated); self.assertEqual(costs['ads_cost'],'275.00')
        self.assertEqual(costs['supplier_delivery_max'],'160.00'); self.assertEqual(costs['customer_delivery_charge'],'75.00')
        self.assertEqual(calculate_price(500,costs)['suggested_price'],'1020.92')

    def test_rate_profiles_reject_malformed_or_dangerous_values(self):
        for mutation in ('negative','descending','bad_max','bad_url','bad_rule'):
            profiles=deepcopy(initial_courier_profiles())
            rule=profiles[0]['zones']['dhaka']
            if mutation=='negative': rule['bands'][0]['charge']=-1
            if mutation=='descending': rule['bands'][1]['up_to_grams']=1
            if mutation=='bad_max': rule['max_weight_grams']=500
            if mutation=='bad_url': profiles[0]['source_url']='javascript:alert(1)'
            if mutation=='bad_rule': profiles[0]['zones']['dhaka']=None
            with self.assertRaises(ValueError): normalize_profiles(profiles)


class WeightIntegrationTests(TransactionTestCase):
    databases={'default','ecommerce'}
    setUp=fixtures.CheckoutHardeningTests.setUp
    cart=fixtures.CheckoutHardeningTests.cart
    payload=fixtures.CheckoutHardeningTests.payload
    csv_file=fixtures.CheckoutHardeningTests.csv_file

    def staff(self):
        self.user.is_staff=self.user.is_superuser=True; self.user.save()

    def test_known_weight_quantity_and_checkout_snapshot(self):
        self.variant.weight_grams=500; self.variant.save(using='ecommerce')
        cart=self.cart()
        self.client.post(f"/api/ecommerce/cart/{cart['token']}/",{'variant_id':self.variant.pk,'quantity':1},format='json')
        data=self.payload(cart); data['shipping_address']['thana']='Dhanmondi'
        quote=self.client.post('/api/ecommerce/checkout/quote/',data,format='json')
        self.assertEqual(quote.data['delivery_details']['weight_grams'],1000)
        self.assertEqual(Decimal(quote.data['shipping_total']),75)
        data['quoted_total']=str(quote.data['grand_total'])
        placed=self.client.post('/api/ecommerce/checkout/',data,format='json')
        self.assertEqual(placed.status_code,201,placed.data)
        saved=Order.objects.using('ecommerce').get(number=placed.data['number'])
        self.assertEqual(saved.delivery_quote['weight_grams'],1000)
        DeliverySettings.objects.using('ecommerce').create(courier_profiles=[initial_courier_profiles()[0]])
        saved.refresh_from_db(using='ecommerce'); self.assertEqual(saved.shipping_total,75)

    def test_unknown_weight_fallback_is_labelled_not_fake_measurement(self):
        quote=self.client.post('/api/ecommerce/checkout/quote/',self.payload(self.cart()),format='json')
        self.assertEqual(quote.data['delivery_details']['fallback'],'missing_product_weight')
        self.assertTrue(quote.data['delivery_details']['estimated_weight'])
        self.assertEqual(Decimal(quote.data['shipping_total']),80)

    def test_checkout_uses_area_and_weight_together(self):
        cart=self.cart()
        for grams, metro, outside in [(500,70,135),(1000,75,145),(2000,100,175)]:
            self.variant.weight_grams=grams; self.variant.save(using='ecommerce')
            for district,thana,zone,fee in [('Dhaka','Dhanmondi','dhaka',metro),('ঢাকা','ধানমন্ডি','dhaka',metro),
                                           ('Chattogram','Kotwali','outside',outside)]:
                with self.subTest(grams=grams,district=district):
                    data=self.payload(cart,district); data['shipping_address']['thana']=thana
                    response=self.client.post('/api/ecommerce/checkout/quote/',data,format='json')
                    self.assertEqual(response.status_code,200,response.data)
                    self.assertEqual(response.data['delivery_details']['zone'],zone)
                    self.assertEqual(response.data['delivery_details']['weight_grams'],grams)
                    self.assertEqual(Decimal(response.data['shipping_total']),fee)
        self.assertEqual(Order.objects.using('ecommerce').count(),0)

    def test_central_defaults_are_private_validated_and_apply_without_repricing(self):
        self.staff()
        public=self.guest.get('/api/ecommerce/store-policy/').json()
        self.assertNotIn('cost_defaults',public); self.assertNotIn('courier_profiles',public)
        self.assertEqual(public['delivery_calculation'],'weight_range_midpoint')
        defaults=self.client.get('/api/ecommerce/admin/pricing/preview/').json()
        self.assertEqual(defaults['costs']['ads_cost'],'275.00')
        preview=self.client.post('/api/ecommerce/admin/pricing/preview/',{'source_cost':500,'use_defaults':True,'weight_grams':1000},format='json')
        self.assertEqual(preview.data['suggested_price'],'1020.92')
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.price,1000)
        costs=initial_cost_defaults(); costs['ads_cost']='0'
        changed=self.client.patch('/api/ecommerce/admin/delivery-settings/',{'cost_defaults':costs},format='json')
        self.assertEqual(changed.status_code,200,changed.data)
        preview=self.client.post('/api/ecommerce/admin/pricing/preview/',{'source_cost':500,'use_defaults':True,'weight_grams':1000},format='json')
        self.assertEqual(preview.data['costs']['ads_cost'],'0.00')
        for bad in [{'ads_cost':-1},[],None]:
            self.assertEqual(self.client.patch('/api/ecommerce/admin/delivery-settings/',{'cost_defaults':bad},format='json').status_code,400)
        self.assertEqual(self.client.patch('/api/ecommerce/admin/delivery-settings/',{'courier_profiles':[]},format='json').status_code,400)

    def test_native_and_csv_can_inherit_cost_defaults_without_snapshots(self):
        self.staff()
        data={'product':self.product.pk,'title':'Blue','sku':self.variant.sku,'price':'1000','cost_price':'500',
            'stock':10,'currency':'BDT','low_stock_threshold':5,'weight_grams':1000,'is_active':True,'requires_shipping':True,
            'use_default_costs':True,'apply_suggested_price':True}
        form=ProductVariantAdminForm(data=data,instance=self.variant)
        self.assertTrue(form.is_valid(),form.errors); saved=form.save()
        self.assertEqual(saved.pricing_inputs,{}); self.assertEqual(Decimal(saved.price),Decimal('1020.92'))
        row={'Handle':self.product.slug,'Title':'Product','SKU':self.variant.sku,'Cost Per Item':'500',
             'Use Default Costs':'TRUE','Apply Calculated Price':'TRUE'}
        response=self.client.post('/api/ecommerce/admin/import/products/',{'file':self.csv_file(row)})
        self.assertEqual(response.data['failed'],0,response.data)
        self.variant.refresh_from_db(using='ecommerce'); self.assertEqual(self.variant.pricing_inputs,{})
        self.assertEqual(self.variant.weight_grams,1000)

    def test_stale_weight_rate_quote_is_rejected_before_order_or_wallet_write(self):
        self.variant.weight_grams=500; self.variant.save(using='ecommerce')
        data=self.payload(self.cart()); data['quoted_total']=str(self.client.post('/api/ecommerce/checkout/quote/',data,format='json').data['grand_total'])
        DeliverySettings.objects.using('ecommerce').create(courier_profiles=[initial_courier_profiles()[0]])
        response=self.client.post('/api/ecommerce/checkout/',data,format='json')
        self.assertEqual(response.status_code,409,response.data)
        self.assertEqual(Order.objects.using('ecommerce').count(),0)
