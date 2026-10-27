from decimal import Decimal
from django.utils import timezone
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from .test_supplier_source_publish import SourcePublicationTests
from .test_suppliers import SupplierTests
from .models import Product, ProductVariant, ProductImage, Category, SupplierOffer, Order
from .supplier_service import screen
from .supplier_source_publish import publish_source


class SupplierRepairTests(TestCase):
    databases = {'default', 'ecommerce'}
    setUp = SourcePublicationTests.setUp

    def test_authenticated_selfshop_restores_payable_price_not_lower_internal_cost(self):
        from .supplier_source_repair import restore_observations
        from .models import Supplier
        self.supplier=Supplier.objects.create(pk=4,name='SelfShop',website='https://selfshop.com.bd',enabled=True,terms_confirmed=True)
        self.source.supplier=self.supplier
        self.source.prices={'pricing_locked':False,'ProductWholesalePrice':{'amount':'440'},'storefront_price':{'amount':'484'}}
        self.source.extra={'account_authenticated':True}
        self.source.stock={'status':'Active','qty':400,'minimum_qty':1};self.source.save()
        offer=SupplierOffer.objects.create(supplier=self.supplier,source_product=self.source,external_id='selfshop-test',title='Shirt',url=self.source.url)
        self.assertEqual(restore_observations(self.source.pk),1)
        offer.refresh_from_db()
        self.assertEqual(offer.source_price,Decimal('484'))
        self.assertEqual(offer.quantity,400)
        self.assertEqual(offer.availability,'in_stock')
        self.assertEqual(ProductVariant.objects.count(),0)

    def test_negative_source_observation_replaces_unknown_not_newer_offer(self):
        from .supplier_source_repair import restore_observations
        from datetime import timedelta
        self.source.stock={'status':'out_of_stock'};self.source.save()
        offer=SupplierOffer.objects.create(supplier=self.supplier,source_product=self.source,external_id='old',title='Old',url=self.source.url)
        self.assertEqual(restore_observations(self.source.pk),1)
        offer.refresh_from_db();self.assertEqual(offer.availability,'out_of_stock')
        offer.availability='in_stock';offer.observed_at=timezone.now()+timedelta(seconds=1);offer.save()
        self.assertEqual(restore_observations(self.source.pk),0)

    def test_price_preview_has_no_invented_price_and_no_purchasable_variant(self):
        category = Category.objects.create(name='Electronics', slug='electronics')
        product = Product.objects.create(name='Price pending product', slug='price-pending', category=category,
            status='active', description='Original product details', attributes={'_catalog_price_preview':True})
        SupplierOffer.objects.create(supplier=self.supplier, external_id='P1', vendor_id='test', title=product.name,
            url=self.source.url, source_product=self.source, imported_product=product, source_price=None)
        media = self.source.media.get()
        media.metadata={'verified_image':True};media.save()
        ProductImage.objects.create(product=product, source_media=media, url=media.original_url)
        listing = APIClient().get('/api/ecommerce/products/').data
        self.assertEqual(listing['count'], 1)
        self.assertIsNone(listing['results'][0]['price'])
        self.assertTrue(listing['results'][0]['price_on_request'])
        self.assertFalse(listing['results'][0]['purchasable'])
        detail = APIClient().get('/api/ecommerce/products/price-pending/').data
        self.assertEqual(detail['variants'], [])
        self.assertFalse(detail['purchasable'])
        self.assertFalse(Order.objects.exists())

    def test_legacy_category_card_is_reused_for_simple_source(self):
        category = Category.objects.create(name='Electronics', slug='electronics')
        product = Product.objects.create(name='Original product', slug='legacy', category=category, status='draft')
        SupplierOffer.objects.create(supplier=self.supplier, external_id='P1', vendor_id='not-provided',
            variant_id='catalogue-type-1', title=product.name, url=self.source.url, imported_product=product)
        self.source.variants=[];self.source.stock={'quantity':3};self.source.save()
        publish_source(self.source.pk)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(SupplierOffer.objects.get().imported_product_id, product.pk)
        self.assertEqual(ProductVariant.objects.get().cost_price, Decimal('100'))


class MatchScoreTests(TransactionTestCase):
    databases={'default','ecommerce'}
    setUp=SupplierTests.setUp
    row=SupplierTests.row
    offer=SupplierTests.offer
    evidence=SupplierTests.evidence
    ready=SupplierTests.ready

    def test_score_bands_control_research_classification(self):
        offer=self.ready()
        for score, classification, state in [(49,'unique','unique'),(50,'manual_review','needs_review'),
                                            (79,'manual_review','needs_review'),(80,'filtered_candidate','ready'),
                                            (100,'filtered_candidate','ready')]:
            offer.evidence.update(match_confidence=score)
            decision=screen(offer,self.user.pk)
            self.assertEqual(decision.result['matching_status'],classification)
            self.assertEqual(decision.state,state)
