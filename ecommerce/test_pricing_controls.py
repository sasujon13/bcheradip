from decimal import Decimal
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from rest_framework.test import APIClient
from cheradip.models import Customer
from .models import DeliverySettings, ProductVariant, Order, SupplierAudit, SupplierOffer
from .phone_display import local_contact
from .pricing import calculate_price, retail_prices, default_pricing_rules, normalize_pricing_rules
from . import test_supplier_source_publish as source_fixtures
from . import test_checkout_hardening as checkout_fixtures


class PricingAndPhoneRulesTests(SimpleTestCase):
    def test_local_phone_display_does_not_change_international_or_login_identifiers(self):
        for value, country, expected in [('1722710298','BD','01722710298'),
                ('1722710298','+880','01722710298'),('01722710298','BD','01722710298'),
                ('+8801722710298','BD','+8801722710298'),('1722710298','US','1722710298'),
                ('admin','BD','admin'),('teacher@example.com','BD','teacher@example.com')]:
            self.assertEqual(local_contact(value,country),expected)

    def test_inclusive_existing_bands_and_configured_rule(self):
        for cost, rate in [('100','20'),('100.01','19'),('200','19'),('200.01','18'),('1000','11'),('1000.01','10')]:
            self.assertEqual(calculate_price(cost,{})['markup_percent'],rate)
        rules={**default_pricing_rules(),'start_percent':'25','minimum_percent':'15','step_percent':'2','discount_percent':'15'}
        self.assertEqual(calculate_price('200',{},rules=rules)['markup_percent'],'23')
        self.assertEqual(retail_prices('123.01',rules)['sale_price'],'128')
        self.assertEqual(retail_prices('900')['regular_price'],'1000')
        pair=retail_prices('123.01');self.assertEqual(pair['sale_price'],'126')
        self.assertEqual((Decimal(pair['regular_price'])-126)/Decimal(pair['regular_price']),Decimal('.10'))

    def test_invalid_percentage_settings_are_rejected(self):
        for changes in [{'discount_percent':'100'},{'band_size':'0'},{'minimum_percent':'21'},
                        {'step_percent':True},{'start_percent':'NaN'}]:
            with self.assertRaises(ValueError):normalize_pricing_rules({**default_pricing_rules(),**changes})

    def test_sale_badge_uses_fixed_configured_discount_after_display_rounding(self):
        from types import SimpleNamespace
        from .serializers import ProductListSerializer, StorefrontVariantSerializer
        product=SimpleNamespace(attributes={'_retail_pricing':{'5':{'mode':'sale','discount_percent':'10.00'}}},
            default_variant_id=5,price=Decimal('63'),compare_at_price=Decimal('70'))
        self.assertEqual(ProductListSerializer().get_discount_percent(product),10)
        variant=SimpleNamespace(product=product,pk=5,price=Decimal('63'),compare_at_price=Decimal('70'))
        self.assertEqual(StorefrontVariantSerializer().get_discount_percent(variant),10)

    def test_reference_prices_round_to_nearest_ten_after_whole_taka(self):
        from .pricing import round_reference_price_to_ten
        for old, expected in [('1263','1260'),('1117','1120'),('923','920'),
                              ('1260','1260'),('1264','1270'),('60.49','60'),('63.00','60'),('63.50','70'),('64.00','70')]:
            self.assertEqual(round_reference_price_to_ten(old),Decimal(expected))

    def test_ten_percent_is_applied_after_eleven_point_eleven_increase_and_ten_rounding(self):
        for base, reference, sale in [('1136.30','1260','1134'),('1005','1120','1008'),
                                      ('829.14','920','828'),('11369.71','12630','11367')]:
            pair=retail_prices(base)
            self.assertEqual(pair['reference_increase_percent'],'11.11')
            self.assertEqual(pair['regular_price'],reference)
            self.assertEqual(pair['sale_price'],sale)
            self.assertEqual(Decimal(sale),Decimal(reference)*Decimal('.90'))


class CentralPricingApiTests(TestCase):
    databases={'default','ecommerce'}
    setUp=source_fixtures.SourcePublicationTests.setUp
    confirmation_product=source_fixtures.SourcePublicationTests.confirmation_product

    def client_for(self,staff=True,superuser=True):
        user=Customer.objects.create_user(username=f'pricing-{staff}-{superuser}',password='synthetic',is_staff=staff,is_superuser=superuser)
        client=APIClient();client.force_authenticate(user);return client,user

    def test_private_rules_require_permission_and_never_leak_publicly(self):
        client,_=self.client_for(superuser=False)
        self.assertEqual(client.patch('/api/ecommerce/admin/delivery-settings/',{'pricing_rules':default_pricing_rules()},format='json').status_code,403)
        self.assertEqual(client.post('/api/ecommerce/admin/pricing/reprice/',{},format='json').status_code,403)
        self.assertNotIn('pricing_rules',APIClient().get('/api/ecommerce/store-policy/').data)

    def test_save_changes_future_calculations_only_and_invalid_values_do_not_save(self):
        variant=self.confirmation_product();old_price=variant.price;client,_=self.client_for()
        rules={**default_pricing_rules(),'start_percent':'25'}
        response=client.patch('/api/ecommerce/admin/delivery-settings/',{'pricing_rules':rules},format='json')
        self.assertEqual(response.status_code,200,response.data)
        variant.refresh_from_db();self.assertEqual(variant.price,old_price)
        self.assertTrue(SupplierAudit.objects.filter(action='central_pricing_rules_saved').exists())
        response=client.patch('/api/ecommerce/admin/delivery-settings/',{'pricing_rules':{**rules,'discount_percent':'100'}},format='json')
        self.assertEqual(response.status_code,400)
        self.assertEqual(DeliverySettings.current().pricing_rules['discount_percent'],'10.00')

    def test_preview_explicit_apply_no_compounding_and_manual_price_preserved(self):
        variant=self.confirmation_product();client,_=self.client_for();config=DeliverySettings.current()
        config.pricing_rules={**default_pricing_rules(),'start_percent':'30','minimum_percent':'20'};config.save()
        path='/api/ecommerce/admin/pricing/reprice/'
        preview=client.post(path,{},format='json');self.assertEqual(preview.status_code,200,preview.data)
        self.assertEqual(preview.data['counts']['changed'],1)
        variant.refresh_from_db();self.assertEqual(variant.price,Decimal('144'))
        self.assertEqual(client.post(path,{'apply':True},format='json').status_code,409)
        payload={'apply':True,'policy_signature':preview.data['policy_signature'],'upper_bound':preview.data['upper_bound']}
        applied=client.post(path,payload,format='json');self.assertEqual(applied.status_code,200,applied.data)
        variant.refresh_from_db();self.assertEqual(variant.price,Decimal('153'));self.assertEqual(variant.compare_at_price,Decimal('170'))
        repeat=client.post(path,payload,format='json');self.assertEqual(repeat.data['counts']['unchanged'],1)
        variant.price=Decimal('166');variant.save()
        preserved=client.post(path,payload,format='json');self.assertEqual(preserved.data['counts']['manual_prices_preserved'],1)
        variant.refresh_from_db();self.assertEqual(variant.price,Decimal('166'));self.assertFalse(Order.objects.exists())

    def test_changed_settings_invalidate_preview(self):
        self.confirmation_product();client,_=self.client_for();path='/api/ecommerce/admin/pricing/reprice/'
        preview=client.post(path,{},format='json').data
        config=DeliverySettings.current();config.pricing_rules={**default_pricing_rules(),'discount_percent':'15'};config.save()
        self.assertEqual(client.post(path,{'apply':True,'policy_signature':preview['policy_signature']},format='json').status_code,409)

    def test_direct_admin_pricing_changes_invalidate_old_screening_fingerprints(self):
        from .supplier_service import fingerprint,policy
        self.confirmation_product();offer=SupplierOffer.objects.get(source_product=self.source)
        before=fingerprint(offer,policy())
        config=DeliverySettings.current();config.pricing_rules={**default_pricing_rules(),'start_percent':'25'};config.save()
        self.assertNotEqual(fingerprint(offer,policy()),before)

    def test_malformed_generated_metadata_is_preserved_not_a_server_error(self):
        variant=self.confirmation_product();client,_=self.client_for();product=variant.product
        product.attributes['_retail_pricing'][str(variant.pk)]['applied_price']='not-money';product.save()
        response=client.post('/api/ecommerce/admin/pricing/reprice/',{},format='json')
        self.assertEqual(response.status_code,200,response.data);self.assertEqual(response.data['counts']['manual_prices_preserved'],1)


class CheckoutPresentationTests(TransactionTestCase):
    databases={'default','ecommerce'}
    setUp=checkout_fixtures.CheckoutHardeningTests.setUp
    cart=checkout_fixtures.CheckoutHardeningTests.cart
    payload=checkout_fixtures.CheckoutHardeningTests.payload

    def test_rounding_is_payable_and_stored_not_just_display_formatting(self):
        self.variant.price=Decimal('1000.10');self.variant.save()
        payload=self.payload(self.cart());payload['phone']='1722710298';payload['phone_alternate']='1822710298'
        quote=self.client.post('/api/ecommerce/checkout/quote/',payload,format='json')
        self.assertEqual(quote.status_code,200,quote.data)
        self.assertEqual(Decimal(quote.data['grand_total']),Decimal('1091'))
        self.assertEqual(Decimal(quote.data['rounding_adjustment']),Decimal('.90'))
        order=self.client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(order.status_code,201,order.data)
        saved=Order.objects.get();self.assertEqual(saved.grand_total,Decimal('1091'))
        self.assertEqual(saved.delivery_quote['rounding_adjustment'],'0.90')
        self.assertEqual(saved.phone,'01722710298');self.assertEqual(saved.shipping_address['phone_alternate'],'01822710298')

    def test_profile_phone_display_preserves_account_identifier(self):
        self.user.username='1722710298';self.user.country_code='+880';self.user.save()
        response=self.client.get('/api/ecommerce/checkout/profile/')
        self.assertEqual(response.status_code,200,response.data);self.assertEqual(response.data['phone'],'01722710298')
        self.user.refresh_from_db();self.assertEqual(self.user.username,'1722710298')
