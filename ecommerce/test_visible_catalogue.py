from copy import deepcopy
from unittest.mock import patch
from django.test import TestCase,SimpleTestCase,override_settings
from django.utils import timezone
from . import test_supplier_source_publish as source_fixtures
from .supplier_visible_catalogue import labelled_card_quote,record_browser_observation,source_for_card,visible_labelled_price,visible_stock
from .supplier_source_publish import source_variants,publish_source
from .supplier_recollection import save_record
from .models import SupplierSourceProduct,SupplierRecollectionRun,Product,SupplierOffer


class BrowserQuoteParsingTests(SimpleTestCase):
    def test_rendered_buying_label_and_stock_are_required_not_hidden_metadata(self):
        text='Market Price: 900\nReseller Price: 550\nস্টক: ১২'
        self.assertEqual(visible_labelled_price(text,'Reseller Price'),'550.00')
        self.assertEqual(visible_stock(text),('in_stock',12))
        self.assertIsNone(visible_labelled_price('Suggested Price: 550','Wholesale Price'))
        self.assertIsNone(visible_labelled_price('Wholesale Price: 500 Wholesale Price: 900','Wholesale Price'))
        self.assertEqual(visible_stock('In Stock\nOut of Stock'),('unconfirmed',None))
    def test_only_explicit_account_buying_labels_are_cost(self):
        self.assertEqual(labelled_card_quote({'price_label':'আপনার পাইকারি মূল্য','price':'৳860'}),'860.00')
        for label,price in [('Suggested Price','৳950'),('Estimated Profit','৳300'),('Wholesale Price','৳100–200'),('Wholesale Price','0')]:
            self.assertIsNone(labelled_card_quote({'price_label':label,'price':price}))


class BrowserIntakeTests(TestCase):
    databases={'default','ecommerce'}
    setUp=source_fixtures.SourcePublicationTests.setUp
    def proof(self,**kwargs):
        return {'state':'verified','method':'rendered_browser_dom','checked_at':timezone.now().isoformat(),
            'buying_price':'100.00','price_label':'Your wholesale price','product_url':self.source.url,
            'stock_status':'in_stock','quantity':None,'quantity_verified':False,**kwargs}

    @override_settings(SUPPLIER_BROWSER_VISIBLE_INTAKE=True)
    def test_new_publication_needs_browser_proof_and_does_not_create_duplicates(self):
        with self.assertRaisesMessage(ValueError,'browser-visible'):
            publish_source(self.source.pk)
        self.assertEqual(Product.objects.count(),0)
        record_browser_observation(self.source.pk,self.proof())
        self.assertEqual(publish_source(self.source.pk),{'published':1})
        self.assertEqual(publish_source(self.source.pk),{'published':1})
        self.assertEqual(Product.objects.count(),1)

    def test_browser_simple_price_wins_and_unspecified_quantity_is_not_invented(self):
        self.source.variants=[];self.source.save()
        record_browser_observation(self.source.pk,self.proof(buying_price='110.00'))
        self.source.refresh_from_db();row=source_variants(self.source)[0]
        self.assertEqual(str(row['cost']),'110.00');self.assertIsNone(row['quantity'])
        self.assertTrue(row['confirmation_required'])

    def test_structured_followup_cannot_replace_browser_preferred_content(self):
        record_browser_observation(self.source.pk,self.proof())
        old_media=list(self.source.media.values_list('id','last_run_id'))
        newer=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='running')
        incoming={**deepcopy(self.record),'description':'Different hidden API description',
            'prices':{'baseCost':{'amount':'999'}},'media':[{'url':'https://cdn.businesskoro.com/products/different.jpg'}]}
        save_record(newer.pk,incoming);self.source.refresh_from_db()
        self.assertEqual(self.source.description,self.record['description'])
        self.assertEqual(self.source.extra['browser_verification']['buying_price'],'100.00')
        self.assertEqual(self.source.extra['latest_structured_observation']['product']['description'],incoming['description'])
        self.assertEqual(list(self.source.media.values_list('id','last_run_id')),old_media)

    def test_same_title_without_an_exact_reference_does_not_relink_an_offer(self):
        self.assertIsNone(source_for_card(self.supplier.pk,{'title':self.source.title,'url':'https://www.businesskoro.com/unrelated'}))
        self.assertEqual(source_for_card(self.supplier.pk,{'title':'Changed marketing title','url':self.source.url}).pk,self.source.pk)

    def test_api_enrichment_reuses_a_browser_derived_source_with_the_same_original_url(self):
        self.source.extra={**self.source.extra,'identity_origin':'browser_url','browser_preferred':True,
            'browser_verification':self.proof()};self.source.save()
        newer=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='running')
        incoming={**deepcopy(self.record),'external_id':'real-provider-id-after-browser-discovery'}
        save_record(newer.pk,incoming)
        self.assertEqual(SupplierSourceProduct.objects.count(),1)
        self.source.refresh_from_db()
        self.assertEqual(self.source.extra['latest_structured_observation']['product']['external_id'],incoming['external_id'])

    def test_browser_options_keep_unknown_per_option_quantities_instead_of_parent_total(self):
        proof=self.proof(visible_variants=[{'id':'visible-black','spec':{'color':'Black'},'buying_price':'100.00','quantity':None},
            {'id':'visible-white','spec':{'color':'White'},'buying_price':'110.00','quantity':None}])
        record_browser_observation(self.source.pk,proof);self.source.refresh_from_db()
        rows=source_variants(self.source)
        self.assertEqual([str(r['cost']) for r in rows],['100.00','110.00'])
        self.assertEqual([r['quantity'] for r in rows],[None,None])
        self.assertTrue(all(r['confirmation_required'] for r in rows))

    def test_conflicting_api_quote_cannot_override_browser_cost_and_equal_string_price_is_valid(self):
        from .supplier_service import snapshot_row
        publish_source(self.source.pk)
        record_browser_observation(self.source.pk,self.proof())
        offer=SupplierOffer.objects.get()
        row={k:getattr(offer,k) for k in ('external_id','variant_id','vendor_id','warehouse_id','identity','title','quantity')}
        row.update(source_price='999.00',availability='in_stock',observed_at=timezone.now().isoformat())
        self.assertEqual(snapshot_row(self.supplier,row,update=True),'conflict')
        offer.refresh_from_db();self.assertEqual(str(offer.source_price),'100.00')
        row.update(source_price='100.00',observed_at=timezone.now().isoformat())
        self.assertEqual(snapshot_row(self.supplier,row,update=True),'updated')
