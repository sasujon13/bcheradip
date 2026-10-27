"""Isolated source-staging tests. No real credentials, source calls or commerce records."""
from copy import deepcopy
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from .models import Supplier, SupplierRecollectionRun, SupplierSourceProduct, SupplierSourceMedia, SupplierRecollectionItem, Category, Product, SupplierOffer, ProductImage
from .supplier_recollection import save_record, validate_record, reference_url, product_data, apply_missing_content
from .supplier_source_parsers import selfshop, uddoog, business_koro, html_product, dropshipping
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
from django.core.management import call_command
from django.test import override_settings


class SourceValidationTests(SimpleTestCase):
    def test_long_original_supplier_code_is_preserved_instead_of_stopping_catalogue(self):
        original='vendor-original-code-'*80
        record={'external_id':'long-code','title':'Product','url':'https://supplier.example/product',
                'sku':original,'description':'Original complete description','media':[{'url':'https://supplier.example/image.jpg'}]}
        self.assertEqual(validate_record(record)[0]['sku'],original)

    def test_placeholder_description_is_not_fabricated_content_and_short_description_can_supply_real_details(self):
        from .supplier_recollection import preferred_description
        from types import SimpleNamespace
        record={'external_id':'1','title':'Own','url':'https://supplier.example/1','description':'<p>N/A</p>',
            'media':[{'url':'https://supplier.example/own.jpg'}]}
        self.assertIn('description',validate_record(record)[0]['quality']['missing'])
        record['short_description']='<p>Actual original product details</p>'
        self.assertNotIn('description',validate_record(record)[0]['quality']['missing'])
        self.assertEqual(preferred_description(SimpleNamespace(description=record['description'],short_description=record['short_description'])),
            'Actual original product details')
    def test_html_metadata_sku_category_video_and_product_specs_are_preserved_without_using_retail_as_cost(self):
        page='''<html><head><meta property="og:image" content="https://supplier.example/logo.png">
        <script type="application/ld+json">{"@type":"Product","name":"Own item","url":"https://supplier.example/product/own","sku":"REAL-1","brand":{"name":"Actual brand"},"offers":{"price":1850},"additionalProperty":[{"name":"Material","value":"Cotton"}]}</script>
        <script>window.password="never-store-session-script"</script></head><body><h1>Own item</h1>
        <div class="pd-image-col"><img src="/actual.jpg"></div><div class="pd-info-col">
        <div class="pd-price-item-value wholesale">1150</div><div class="pd-price-item-value stock-in">In Stock</div></div>
        <div class="pd-sku">SKU: REAL-1 | Category: Clothing</div>
        <div class="pd-desc-content">Complete description<iframe src="https://www.youtube.com/embed/own"></iframe></div></body></html>'''
        record=html_product('dropify','https://supplier.example/product/own',page)
        self.assertEqual(record['sku'],'REAL-1');self.assertEqual(record['categories'],[{'name':'Clothing'}])
        self.assertEqual(record['prices']['wholesale']['amount'],'1150.00')
        self.assertEqual(record['extra']['structured_attributes']['offers']['price'],1850)
        self.assertEqual(record['specifications']['structured_properties'][0]['value'],'Cotton')
        self.assertTrue(any(m.get('kind')=='video' for m in record['media']))
        data,images=validate_record(record)
        self.assertNotIn('never-store-session-script',str(data))
        self.assertFalse(any('logo.png' in m['original_url'] for m in images))
        self.assertIn('og:image',data['extra']['html_metadata']['meta'])  # Evidence only, not gallery.

    def test_related_schema_does_not_become_own_product_and_unavailable_first_label_wins(self):
        page='''<html><head><script type="application/ld+json">{"@type":"Product","name":"Other","url":"https://supplier.example/product/other","sku":"OTHER"}</script></head>
        <body><div class="product-details-page"><div id="descriptionCopy">Full original description</div>
        প্রাইস: 100 স্টক: নেই <div>Related স্টক: আছে</div></div></body></html>'''
        record=html_product('shopbase','https://supplier.example/product/own',page,title='Own')
        self.assertEqual(record['stock']['status'],'out_of_stock')
        self.assertNotIn('প্রাইস',record['description'])
        self.assertFalse(record.get('sku'));self.assertEqual(record['extra']['html_metadata']['structured_products'],[])

    def test_relative_uddoog_variant_image_keeps_its_source_origin_and_relationship(self):
        record=uddoog({'id':'1','slug':'own','name':'Own','variants':[{'id':'v1','image':'/red.jpg'}]})
        self.assertEqual(record['media'][0]['url'],'https://dropshop.com.bd/red.jpg')
        self.assertEqual(record['media'][0]['variant_id'],'v1')
        record=business_koro({'id':'1','slug':'own','name':'Own','variants':[{'id':'v1','image':'https://cdn.businesskoro.com/red.jpg'}]})
        self.assertEqual(record['media'][0]['url'],'https://cdn.businesskoro.com/red.jpg')

    def test_source_cannot_supply_forged_local_image_verification(self):
        data,images=validate_record({'external_id':'1','url':'https://supplier.example/1','title':'Own',
            'description':'Full','media':[{'url':'https://supplier.example/own.jpg','metadata':
                {'verified_image':True,'cached_name':'supplier_products/other.jpg','sha256':'fake','custom_source_field':'keep'}}]})
        self.assertEqual(images[0]['metadata'],{'custom_source_field':'keep'})
    def test_reseller_price_is_not_retail_and_negative_stock_is_never_available(self):
        p={'id':7,'slug':'own','name':'Own product','sale_price':150,'reselling_price':390,'status':1}
        page='<input id="single_page_product_id" value="7"><input id="product_stock" value="-4"><div id="home">Full description</div>'
        record=dropshipping(p,{'images':[{'product_id':7,'image':'images/products/original.jpg'}]},page,'https://www.dropshipping.com.bd/product/own')
        self.assertEqual(record['prices']['sale_price']['amount'],'150.00')
        self.assertEqual(record['prices']['reselling_price']['amount'],'390.00')
        self.assertEqual(record['stock']['quantity'],-4)
        self.assertEqual(record['stock']['status'],'out_of_stock')
        self.assertIn('/storage/images/products/original.jpg',record['media'][0]['url'])
        with self.assertRaises(ValueError):
            dropshipping(p,{'images':[{'product_id':8,'image':'unrelated.jpg'}]},page,'https://www.dropshipping.com.bd/product/own')
    def test_signed_in_dropify_labels_ignore_css_and_preserve_unknown_quantity(self):
        page = '''<html><style>.stock-out { content: 'স্টকে নেই'; }</style><h1>Own item</h1>
        <div class="pd-image-col"><img src="/own.jpg"></div><div class="pd-info-col">
        <div class="pd-price-item-value suggested">৳1,850</div>
        <div class="pd-price-item-value wholesale">৳1,150</div>
        <div class="pd-price-item-value stock-in">In Stock</div>
        <div class="pd-min-selling">Minimum <strong>৳1,850</strong></div></div>
        <div class="pd-desc-content">Actual full description.</div></html>'''
        record = html_product('dropify', 'https://supplier.example/product/own', page)
        self.assertEqual(record['prices']['wholesale']['amount'], '1150.00')
        self.assertEqual(record['prices']['minimum_selling_price']['amount'], '1850.00')
        self.assertEqual(record['stock']['status'], 'in_stock')
        self.assertIsNone(record['stock']['quantity'])
        self.assertTrue(record['extra']['account_price_verified'])
    def test_secret_fields_and_session_urls_are_not_preserved_in_product_data(self):
        original = {'custom_product_field': {'new': 2}, 'password': 'synthetic', 'api_secret': 'synthetic',
                    'images': ['https://supplier.example/photo.jpg?w=800', 'https://supplier.example/photo?token=synthetic']}
        clean = product_data(original)
        self.assertEqual(clean['custom_product_field'], original['custom_product_field'])
        self.assertNotIn('password', clean)
        self.assertNotIn('api_secret', clean)
        self.assertNotIn('synthetic', str(clean))
        self.assertEqual(clean['images'][0], original['images'][0])

    def test_private_or_credential_bearing_references_are_refused(self):
        for value in ['https://127.0.0.1/photo', 'https://localhost/photo', 'https://private.lan/photo',
                      'https://user:password@supplier.example/photo', 'http://supplier.example/photo']:
            with self.assertRaises(ValueError):
                reference_url(value)

    def test_all_30_photos_and_variant_relationships_are_retained_without_logo(self):
        images = [{'url': f'https://supplier.example/image-{n}.jpg'} for n in range(30)]
        images += [deepcopy(images[0]), {'url': images[0]['url'], 'variant_id': 'red', 'role': 'variant'},
                   {'url': 'https://supplier.example/logo.png'}]
        data, media = validate_record({'external_id': 'P1', 'title': 'Original', 'url': 'https://supplier.example/p1',
            'description': '<p>Full original description</p>', 'media': images, 'raw_data': {'new_future_field': {'a': [1, 2]}}})
        self.assertEqual(len(media), 31)
        self.assertEqual(media[-1]['variant_id'], 'red')
        self.assertEqual(len(data['quality']['rejected_media']), 1)
        self.assertEqual(data['raw_data']['new_future_field'], {'a': [1, 2]})

    def test_missing_required_content_is_explicit_never_invented(self):
        data, images = validate_record({'external_id': '1', 'title': 'No source content', 'url': 'https://supplier.example/1'})
        self.assertCountEqual(data['quality']['missing'], ['description', 'product_images'])
        self.assertEqual(images, [])

    def test_selfshop_price_lock_gallery_json_and_nested_variants_are_preserved(self):
        p = {'id': 10, 'ProductSlug': 'shirt', 'ProductName': 'Shirt', 'ProductDetails': '<p>Full</p>',
             'ViewProductImage': 'https://supplier.example/main.jpg', 'PostImage': '["https://supplier.example/back.jpg"]',
             'ProductResellerPrice': None, 'pricing_locked': True, 'varients': [{'id': 9, 'image': 'https://supplier.example/red.jpg',
                 'sizes': [{'id': 8, 'qty': 100, 'price': None}]}], 'future_field': {'b': 2}}
        record = selfshop({'data': {'product_details': p}})
        self.assertTrue(record['prices']['pricing_locked'])
        self.assertIsNone(record['prices']['ProductResellerPrice']['amount'])
        self.assertEqual(record['variants'][0]['sizes'][0]['qty'], 100)
        self.assertEqual(record['raw_data']['product_details']['future_field'], {'b': 2})
        self.assertEqual(record['media'][-1]['variant_id'], '9')

    def test_koro_cost_and_suggested_price_remain_separate(self):
        record = business_koro({'id': 'A', 'slug': 'a', 'name': 'A', 'costPrice': 100, 'suggestedPrice': 150,
                                'description': 'Full', 'image': 'https://supplier.example/main.jpg'})
        self.assertEqual(record['prices']['costPrice']['amount'], '100.00')
        self.assertEqual(record['prices']['suggestedPrice']['amount'], '150.00')

    def test_dropify_related_images_do_not_become_gallery_or_retail_become_cost(self):
        page = '''<html><h1>Own product</h1><div class="pdp-gallery-card"><img src="/own.jpg"><img src="/back.jpg"></div>
        <div class="pdp-short-desc">Overview</div><div class="pdp-desc-content">Complete description</div>
        হোলসেল প্রাইস 1,150 সাজেস্টেড বিক্রয়মূল্য 1,850 স্টক: 100 ইউনিট
        <div class="pdp-related-img"><img src="/another-product.jpg"></div></html>'''
        record = html_product('dropify', 'https://supplier.example/view-product/own', page)
        self.assertEqual([m['url'] for m in record['media']], ['https://supplier.example/own.jpg', 'https://supplier.example/back.jpg'])
        self.assertEqual(record['prices']['wholesale']['amount'], '1150.00')
        self.assertEqual(record['prices']['suggested']['amount'], '1850.00')
        self.assertEqual(record['stock']['quantity'], 100)


class SourceStorageTests(TestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.supplier = Supplier.objects.create(name='Test source', website='https://supplier.example', enabled=True,
                                                terms_confirmed=True, terms_note='Synthetic test')
        self.run = SupplierRecollectionRun.objects.create(supplier=self.supplier, mode='inspect', status='running')
        self.record = {'external_id': 'P1', 'title': 'Original title', 'url': 'https://supplier.example/p1',
                       'description': '<p>Original full content</p>', 'media': [{'url': 'https://supplier.example/own.jpg', 'role': 'main'}]}

    def test_failed_detail_request_does_not_mark_a_seen_product_missing(self):
        from .supplier_recollection import save_failure
        from .management.commands.recollect_supplier_catalogue import missing_sources
        save_record(self.run.pk,self.record)
        save_record(self.run.pk,{**self.record,'external_id':'P2','url':'https://supplier.example/p2'})
        next_run=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='running')
        save_failure(next_run.pk,{'external_id':'P1','url':self.record['url'],'_error':'Detail page timed out'})
        self.assertEqual(list(missing_sources(self.supplier,next_run).values_list('external_id',flat=True)),['P2'])

    def test_resume_is_idempotent_and_new_run_refreshes_original_data_without_losing_media_history(self):
        self.assertEqual(save_record(self.run.pk, self.record), 'complete')
        self.assertEqual(save_record(self.run.pk, self.record), 'already_processed')
        self.run.refresh_from_db()
        self.assertEqual(self.run.processed, 1)
        next_run = SupplierRecollectionRun.objects.create(supplier=self.supplier, mode='full', status='running')
        fresh = {**self.record, 'description': '<p>Changed at original source</p>', 'media': [{'url': 'https://supplier.example/fresh.jpg', 'role': 'main'}]}
        save_record(next_run.pk, fresh)
        self.assertEqual(SupplierSourceProduct.objects.count(), 1)
        self.assertEqual(SupplierSourceMedia.objects.count(), 2)
        self.assertEqual(SupplierSourceProduct.objects.get().description, fresh['description'])

    def test_same_original_url_keeps_local_cache_proof_without_pretending_it_was_checked_in_new_run(self):
        save_record(self.run.pk,self.record)
        image=SupplierSourceMedia.objects.get();image.stored_url='/manage/media/supplier_products/original.jpg'
        image.metadata={'verified_image':True,'cached_name':'supplier_products/original.jpg','verified_run_id':str(self.run.pk)};image.save()
        next_run=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='running')
        save_record(next_run.pk,self.record);image.refresh_from_db()
        self.assertEqual(image.last_run_id,next_run.pk);self.assertTrue(image.metadata['verified_image'])
        self.assertEqual(image.metadata['verified_run_id'],str(self.run.pk))
        self.assertTrue(image.stored_url.endswith('original.jpg'))

    def test_reused_supplier_identifier_with_changed_sku_is_quarantined_not_overwritten(self):
        save_record(self.run.pk,{**self.record,'sku':'ORIGINAL'})
        previous=SupplierSourceProduct.objects.get()
        next_run=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='running')
        self.assertEqual(save_record(next_run.pk,{**self.record,'sku':'DIFFERENT','title':'Another item'}),'incomplete')
        previous.refresh_from_db()
        self.assertEqual(previous.sku,'ORIGINAL');self.assertEqual(previous.title,'Original title')
        self.assertIn('identity_review',previous.quality['missing'])
        self.assertEqual(previous.extra['pending_identity_review']['candidate']['sku'],'DIFFERENT')

    def test_completed_fresh_catalogue_marks_unseen_sources_missing_without_deleting_content(self):
        save_record(self.run.pk,self.record)
        save_record(self.run.pk,{**self.record,'external_id':'P2','url':'https://supplier.example/p2'})
        missing=SupplierSourceProduct.objects.get(external_id='P2');before=missing.observed_at
        self.run.status='completed';self.run.processed=3;self.run.mapping_version=2;self.run.save()
        with patch('ecommerce.management.commands.recollect_supplier_catalogue.SourceClient') as factory:
            client=factory.return_value;client.products.return_value=iter([self.record]);client.expected_total=1;client.coverage={'access_gaps':[]}
            call_command('recollect_supplier_catalogue',supplier='shopbase',mode='full',stdout=StringIO())
        missing.refresh_from_db();self.assertEqual(missing.stock['status'],'missing')
        self.assertEqual(missing.observed_at,before);self.assertTrue(missing.description)
        self.assertEqual(SupplierSourceProduct.objects.count(),2)

    def test_database_interruption_pauses_a_source_run_without_deleting_observations(self):
        from django.db import OperationalError,connections
        from django.core.management.base import CommandError
        self.run.status='completed';self.run.mapping_version=2;self.run.processed=3;self.run.save()
        with patch('ecommerce.management.commands.recollect_supplier_catalogue.SourceClient') as factory, \
             patch('ecommerce.management.commands.recollect_supplier_catalogue.save_record',side_effect=OperationalError('Synthetic disconnect')), \
             patch.object(connections['ecommerce'],'close'):
            factory.return_value.products.return_value=iter([self.record])
            factory.return_value.coverage={'access_gaps':[]}
            with self.assertRaises(CommandError):
                call_command('recollect_supplier_catalogue',supplier='shopbase',mode='full',stdout=StringIO())
        run=SupplierRecollectionRun.objects.filter(mode='full').latest('created_at')
        self.assertEqual(run.status,'paused');self.assertIn('retained',run.activity)

    def test_coordinator_inspects_all_accessible_suppliers_before_full_collection(self):
        from .supplier_source_clients import SUPPLIER_IDS
        Supplier.objects.create(pk=7,name='Second source',website='https://supplier2.example',enabled=True,terms_confirmed=True)
        calls=[]
        def run(name,**params):
            if name=='recollect_supplier_catalogue':
                calls.append((params['mode'],params['supplier']))
                SupplierRecollectionRun.objects.create(supplier_id=SUPPLIER_IDS[params['supplier']],mode=params['mode'],
                    status='completed',processed=3,mapping_version=2,coverage={'full_traversal':params['mode']=='full'})
            else:calls.append(('publish',params['run_id']))
        with TemporaryDirectory() as directory,override_settings(BASE_DIR=Path(directory)), \
             patch('ecommerce.management.commands.recollect_enriched_supplier_catalogues.SITES',('shopbase','dropify')), \
             patch('ecommerce.management.commands.recollect_enriched_supplier_catalogues.call_command',side_effect=run):
            call_command('recollect_enriched_supplier_catalogues',apply=True,stdout=StringIO())
        self.assertEqual(calls[:2],[('inspect','shopbase'),('inspect','dropify')])
        self.assertEqual(calls[2],('full','shopbase'))

    def test_finished_catalogue_with_release_holds_is_not_reported_as_unconditionally_complete(self):
        import json
        run=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='completed',
            mapping_version=2,coverage={'full_traversal':True,'publication':{
                'status':'completed','counts_this_attempt':{'published':2,'held_sources':1}}})
        with TemporaryDirectory() as directory,override_settings(BASE_DIR=Path(directory)), \
             patch('ecommerce.management.commands.recollect_enriched_supplier_catalogues.call_command') as invoke:
            root=Path(directory)/'private_suppliers'/'recollection';root.mkdir(parents=True)
            path=root/'recollection-v2-state.json'
            path.write_text(json.dumps({'version':2,'suppliers':{'shopbase':{
                'status':'completed','full_run':str(run.pk)}}}),encoding='utf-8')
            call_command('recollect_enriched_supplier_catalogues',supplier='shopbase',apply=True,stdout=StringIO())
            saved=json.loads(path.read_text(encoding='utf-8'))['suppliers']['shopbase']
            self.assertEqual(saved['status'],'completed_with_holds')
            self.assertEqual(saved['publication_counts']['held_sources'],1)
            invoke.assert_not_called()
            run.coverage['publication_followup']={'resolved_source_ids':['P1'],'counts':{'published':1}}
            run.save()
            call_command('recollect_enriched_supplier_catalogues',supplier='shopbase',apply=True,stdout=StringIO())
            saved=json.loads(path.read_text(encoding='utf-8'))['suppliers']['shopbase']
            self.assertEqual(saved['status'],'completed')
            self.assertEqual(saved['publication_counts']['published'],3)
            self.assertEqual(saved['publication_counts']['held_sources'],0)
            invoke.assert_not_called()

    def test_only_missing_listing_content_is_filled_without_changing_manual_edits_or_prices(self):
        save_record(self.run.pk, self.record)
        category = Category.objects.create(name='Test', slug='test')
        product = Product.objects.create(name='Staff edited title', slug='staff', category=category, description='Staff edited description')
        offer = SupplierOffer.objects.create(supplier=self.supplier, external_id='P1', vendor_id='original', title='Old card title',
            url=self.record['url'], source_price='100', imported_product=product)
        source = SupplierSourceProduct.objects.get()
        apply_missing_content(source.pk)
        product.refresh_from_db(); offer.refresh_from_db()
        self.assertEqual(product.name, 'Staff edited title')
        self.assertEqual(product.description, 'Staff edited description')
        self.assertEqual(str(offer.source_price), '100.00')
        self.assertEqual(ProductImage.objects.get().source_media.product_id, source.pk)
        apply_missing_content(source.pk)
        self.assertEqual(ProductImage.objects.count(), 1)

    def test_cancelled_run_does_not_write_products(self):
        self.run.status = 'cancel_requested'; self.run.save()
        with self.assertRaises(ValueError):
            save_record(self.run.pk, self.record)
        self.assertEqual(SupplierSourceProduct.objects.count(), 0)
