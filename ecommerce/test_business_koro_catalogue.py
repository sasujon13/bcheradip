from decimal import Decimal
from django.test import TransactionTestCase
from .models import Supplier, SupplierOffer, SupplierAudit, Product
from .business_koro_catalogue import import_catalogue


class BusinessKoroBrowserTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.supplier = Supplier.objects.using('ecommerce').create(name='Browser source', website='https://www.businesskoro.com',
            connector='business_koro', enabled=True, terms_confirmed=True, terms_note='Test permitted reseller catalogue')

    def card(self, **values):
        return dict(url='https://www.businesskoro.com/dashboard/products/exact-item', title='Exact item',
            price='৳100', price_label='আপনার পাইকারি মূল্য', retail_text='৳300 – ৳500', stock_text='In stock', **values)

    def test_only_labelled_buying_price_creates_staging_identity(self):
        result = import_catalogue(self.supplier, [self.card()])
        self.assertEqual(result['counts']['new'], 1)
        offer = SupplierOffer.objects.using('ecommerce').get()
        self.assertEqual(offer.source_price, Decimal('100'))
        self.assertIsNone(offer.quantity); self.assertFalse(offer.single_unit)
        self.assertFalse(offer.match_confirmed); self.assertEqual(offer.state, 'needs_review')
        self.assertTrue(offer.external_id.startswith('url-'))
        self.assertEqual(Product.objects.using('ecommerce').count(), 0)

    def test_retail_profit_ranges_and_foreign_origin_are_not_source_quotes(self):
        for change in ({'price_label':'Estimated profit'}, {'price_label':'Suggested retail price'},
                       {'price':'৳100 – ৳200'}, {'url':'https://other.example/dashboard/products/item'}):
            card = self.card(); card.update(change)
            self.assertEqual(import_catalogue(self.supplier, [card])['counts']['failed'], 1)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 0)

    def test_membership_cards_remain_audited_unpriced_holds(self):
        cards = [dict(url='https://www.businesskoro.com/dashboard/membership?requiredPackage=package',
            title=f'Locked {n}', access_required=True, stock_text='Required: Ultimate Business Setup') for n in range(8)]
        result = import_catalogue(self.supplier, cards)
        self.assertEqual(result['counts']['access_required'], 8)
        self.assertEqual(result['unique_cards'], 8)
        self.assertEqual(result['accessible_product_urls'], 0)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 0)

    def test_new_membership_restriction_invalidates_old_available_quote_without_zeroing_price(self):
        SupplierOffer.objects.using('ecommerce').create(supplier=self.supplier, external_id='old-api-id', vendor_id='vendor',
            title='Locked item', url='https://www.businesskoro.com/dashboard/products#old-api-id', source_price=100,
            quantity=10, availability='in_stock', match_confirmed=True, state='ready')
        import_catalogue(self.supplier,[{'url':'https://www.businesskoro.com/dashboard/membership?requiredPackage=package',
            'title':'Locked item','access_required':True}])
        offer=SupplierOffer.objects.using('ecommerce').get()
        self.assertEqual(offer.availability,'unconfirmed'); self.assertIsNone(offer.quantity)
        self.assertFalse(offer.match_confirmed); self.assertEqual(offer.state,'needs_data')
        self.assertEqual(offer.source_price,Decimal('100'))

    def test_api_variants_keep_ids_and_quantities_when_reference_is_enriched(self):
        for variant in ('L','XL'):
            SupplierOffer.objects.using('ecommerce').create(supplier=self.supplier, external_id='uuid-parent',
                variant_id=variant, vendor_id='not-provided', title='Exact item', source_price=100, quantity=12,
                url='https://www.businesskoro.com/dashboard/products#uuid-parent')
        result = import_catalogue(self.supplier, [self.card()])
        self.assertEqual(result['counts']['reference_enriched'], 1)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 2)
        for offer in SupplierOffer.objects.using('ecommerce').all():
            self.assertEqual(offer.url, self.card()['url']); self.assertEqual(offer.external_id,'uuid-parent')
            self.assertEqual(offer.quantity,12); self.assertEqual(offer.source_price,Decimal('100'))
        self.assertEqual(import_catalogue(self.supplier, [self.card()])['counts']['existing'],1)

    def test_changed_card_quote_invalidates_old_confirmation_without_fabricating_variant_price(self):
        import_catalogue(self.supplier, [self.card()])
        SupplierOffer.objects.using('ecommerce').update(match_confirmed=True, state='ready')
        row = self.card(); row['price']='৳110'
        self.assertEqual(import_catalogue(self.supplier,[row])['counts']['quote_changed'],1)
        offer = SupplierOffer.objects.using('ecommerce').get()
        self.assertFalse(offer.match_confirmed); self.assertEqual(offer.state,'needs_review')
        self.assertEqual(offer.source_price,Decimal('100'))
        latest = SupplierAudit.objects.using('ecommerce').filter(action='browser_buying_price_observed').first()
        self.assertEqual(latest.detail['buying_price'],'110.00')

    def test_duplicate_cards_are_not_duplicate_identities_and_restricted_cards_stay_out(self):
        restricted = self.card(); restricted['title']='928 Stun Gun'; restricted['url']='https://www.businesskoro.com/dashboard/products/restricted'
        result=import_catalogue(self.supplier,[self.card(),self.card(),restricted])
        self.assertEqual(result['counts']['new'],1)
        self.assertEqual(result['counts']['duplicate_on_source'],1)
        self.assertEqual(result['counts']['restricted_skipped'],1)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(),1)

    def test_different_api_quote_is_held_not_overwritten_or_duplicated(self):
        SupplierOffer.objects.using('ecommerce').create(supplier=self.supplier,external_id='uuid-parent',vendor_id='not-provided',
            title='Exact item',source_price=95,match_confirmed=True,state='ready',url='https://www.businesskoro.com/dashboard/products#uuid-parent')
        result=import_catalogue(self.supplier,[self.card()])
        self.assertEqual(result['counts']['conflict'],1)
        offer=SupplierOffer.objects.using('ecommerce').get()
        self.assertFalse(offer.match_confirmed); self.assertEqual(offer.source_price,Decimal('95'))
