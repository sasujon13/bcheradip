from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
import tempfile
from pathlib import Path
from django.test import TestCase
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from .models import (Supplier, SupplierRecollectionRun, SupplierSourceProduct, SupplierOffer, Product,
                     ProductImage, ProductVariant, DeliverySettings)
from .supplier_recollection import save_record
from .supplier_source_publish import publish_source, source_variants


class SourcePublicationTests(TestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        from .supplier_service import policy
        config=policy(); config.catalogue_mode='all'; config.save()
        self.supplier=Supplier.objects.create(pk=2,name='Business Koro test',website='https://www.businesskoro.com',enabled=True,terms_confirmed=True,terms_note='Test')
        DeliverySettings.objects.create(cost_defaults={'ads_cost':'20','packaging_cost':'0','returns_allowance':'0','other_costs':'0'})
        self.run=SupplierRecollectionRun.objects.create(supplier=self.supplier,mode='full',status='running')
        self.record={'external_id':'P1','title':'Original product','url':'https://www.businesskoro.com/dashboard/products/original',
            'description':'<p>Original complete description</p>', 'categories':[{'name':"Men's Clothing"}], 'prices':{'baseCost':{'amount':'100.00'},'packagingCost':{'amount':'5.00'}},
            'stock':{'quantity':999}, 'variants':[{'id':'real-red-l','color':{'name':'Red'},'size':{'name':'L'},'stockQuantity':3}],
            'media':[{'url':'https://cdn.businesskoro.com/products/original.jpg','role':'main'}],
            'raw_data':{'product':{'status':'ACTIVE'}}}
        save_record(self.run.pk,self.record)
        self.source=SupplierSourceProduct.objects.get()
        self.run.status='completed';self.run.coverage={'full_traversal':True};self.run.save()
        def synthetic_photo(media):
            media.stored_url='/manage/media/supplier_products/synthetic.jpg'
            media.metadata={'verified_image':True};media.save();return media
        self.photo=patch('ecommerce.supplier_source_publish.verify_photo',side_effect=synthetic_photo)
        self.photo.start();self.addCleanup(self.photo.stop)

    def test_original_photos_exact_variant_stock_and_content_are_published_without_supplier_purchase(self):
        self.assertEqual(publish_source(self.source.pk),{'published':1})
        offer=SupplierOffer.objects.get();variant=offer.imported_product.variants.get()
        self.assertEqual(offer.quantity,3);self.assertEqual(variant.stock,3)
        self.assertFalse(variant.allow_backorder);self.assertEqual(variant.option1_value,'Red')
        client=APIClient();listing=client.get('/api/ecommerce/products/').data
        self.assertEqual(listing['count'],1)
        self.assertIn('/supplier_products/',listing['results'][0]['image_url'])
        # Old logos stay in private history but can never become public/cart photos.
        ProductImage.objects.create(product=offer.imported_product,url='https://cheradip.com/assets/cheradip.svg',position=0)
        detail=client.get('/api/ecommerce/products/'+offer.imported_product.slug+'/').data
        self.assertTrue(detail['description']);self.assertTrue(all('cheradip.svg' not in p['url'] for p in detail['images']))
        cart=client.post('/api/ecommerce/cart/',{'variant_id':variant.pk,'quantity':1},format='json')
        self.assertEqual(cart.status_code,200,cart.data)
        self.assertIn('/supplier_products/',cart.data['items'][0]['image_url'])
        from .models import Order
        self.assertFalse(Order.objects.exists())

    def test_old_positive_check_stays_visible_and_requests_staff_refresh(self):
        self.assertEqual(publish_source(self.source.pk), {'published': 1})
        offer = SupplierOffer.objects.get()
        old = timezone.now() - timedelta(days=2)
        offer.observed_at = old
        offer.save(update_fields=['observed_at', 'updated_at'])
        self.source.observed_at = old
        self.source.save(update_fields=['observed_at', 'updated_at'])
        client = APIClient()
        listing = client.get('/api/ecommerce/products/').data
        self.assertEqual(listing['count'], 1)
        slug = offer.imported_product.slug
        refresh = client.post(f'/api/ecommerce/products/{slug}/source-refresh/', {}, format='json')
        self.assertEqual(refresh.status_code, 200, refresh.data)
        self.assertTrue(refresh.data['stale'])
        self.assertEqual(refresh.data['state'], 'staff_check_needed')
        from .models import CommerceNotification
        self.assertEqual(CommerceNotification.objects.filter(title='Supplier stock check needs attention').count(), 1)
        client.post(f'/api/ecommerce/products/{slug}/source-refresh/', {}, format='json')
        self.assertEqual(CommerceNotification.objects.filter(title='Supplier stock check needs attention').count(), 1)

    def test_only_source_held_stale_listings_are_restored(self):
        self.assertEqual(publish_source(self.source.pk), {'published': 1})
        offer = SupplierOffer.objects.get()
        product = offer.imported_product
        offer.observed_at = timezone.now() - timedelta(days=2)
        offer.save(update_fields=['observed_at', 'updated_at'])
        product.status = 'archived'
        product.attributes = {**product.attributes, 'source_stock_hold': True}
        product.save(update_fields=['status', 'attributes', 'updated_at'])
        call_command('restore_stale_source_listings')
        product.refresh_from_db()
        self.assertEqual(product.status, 'active')
        self.assertFalse(product.attributes['source_stock_hold'])
        product.status = 'archived'
        product.save(update_fields=['status', 'updated_at'])
        call_command('restore_stale_source_listings')
        product.refresh_from_db()
        self.assertEqual(product.status, 'archived')

    def test_product_detail_queues_one_scoped_background_check(self):
        self.assertEqual(publish_source(self.source.pk), {'published': 1})
        offer = SupplierOffer.objects.get()
        offer.observed_at = timezone.now() - timedelta(days=2)
        offer.save(update_fields=['observed_at', 'updated_at'])
        self.supplier.connector = 'business_koro'
        self.supplier.credentials_ciphertext = 'encrypted-test-placeholder'
        self.supplier.save(update_fields=['connector', 'credentials_ciphertext', 'updated_at'])
        url = f'/api/ecommerce/products/{offer.imported_product.slug}/source-refresh/'
        client = APIClient()
        first = client.post(url, {}, format='json')
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(first.data['state'], 'queued')
        from .models import SupplierJob
        job = SupplierJob.objects.get()
        self.assertEqual(job.payload['offer_ids'], [offer.pk])
        second = client.post(url, {}, format='json')
        self.assertEqual(second.data['state'], 'checking')
        self.assertEqual(SupplierJob.objects.count(), 1)

    def confirmation_product(self):
        supplier=Supplier.objects.create(pk=1,name='ShopBase test',website='https://shopbasebd.com',enabled=True,terms_confirmed=True)
        self.source.supplier=supplier;self.source.variants=[];self.source.extra={}
        self.source.prices={'reseller_price':{'amount':'100'}}
        self.source.stock={'status':'in_stock','quantity':None};self.source.save()
        publish_source(self.source.pk)
        return ProductVariant.objects.get()

    def pending_payload(self, client, variant):
        cart=client.post('/api/ecommerce/cart/',{'variant_id':variant.pk,'quantity':2},format='json')
        self.assertEqual(cart.status_code,200,cart.data)
        self.assertFalse(cart.data['items'][0]['stock_confirmation_required'])
        self.assertTrue(cart.data['items'][0]['quantity_unspecified'])
        return {'cart_token':cart.data['token'],'customer_name':'Test Customer','email':'customer@example.com',
            'phone':'01710000000','shipping_address':{'country_code':'BD','district':'Dhaka','thana':'Savar','address':'Test Road'},
            'payment_method':'cod'}

    def test_label_only_stock_confirms_orders_without_inventing_inventory(self):
        variant=self.confirmation_product();offer=SupplierOffer.objects.get()
        self.assertIsNone(offer.quantity);self.assertEqual(variant.stock,0);self.assertTrue(variant.allow_backorder)
        client=APIClient();listing=client.get('/api/ecommerce/products/?in_stock=true').data
        self.assertEqual(listing['count'],1);self.assertFalse(listing['results'][0]['stock_confirmation_required'])
        self.assertTrue(listing['results'][0]['quantity_unspecified'])
        self.assertGreaterEqual(listing['results'][0]['discount_percent'],10)
        detail=client.get('/api/ecommerce/products/'+variant.product.slug+'/').data
        self.assertFalse(detail['variants'][0]['stock_confirmation_required'])
        self.assertTrue(detail['variants'][0]['quantity_unspecified'])
        payload=self.pending_payload(client,variant)
        quote=client.post('/api/ecommerce/checkout/quote/',payload,format='json')
        self.assertEqual(quote.status_code,200,quote.data);self.assertFalse(quote.data['stock_confirmation_required'])
        self.assertTrue(quote.data['order_auto_confirmed']);self.assertIn('subject to supplier fulfilment',quote.data['confirmation_notice'])
        result=client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(result.status_code,201,result.data);self.assertFalse(result.data['stock_confirmation_pending'])
        from .models import Order,Payment,InventoryMovement
        from cheradip.models import WalletOperation
        order=Order.objects.get();self.assertEqual(order.status,'confirmed');self.assertEqual(order.payment_status,'unpaid')
        self.assertIsNotNone(order.confirmed_at);self.assertEqual(order.history.get().status,'confirmed')
        self.assertFalse(Payment.objects.exists());self.assertFalse(InventoryMovement.objects.exists());self.assertFalse(WalletOperation.objects.exists())
        self.assertEqual(order.items.get().quantity,2);self.assertIn('/supplier_products/',order.items.get().image_url)
        variant.refresh_from_db();self.assertEqual(variant.stock,0)
        from .order_service import change_order
        change_order(order.pk,'cancelled');variant.refresh_from_db()
        self.assertEqual(variant.stock,0);self.assertFalse(InventoryMovement.objects.exists())

    def test_label_only_stock_allows_normal_payment_submission_not_false_paid_status(self):
        variant=self.confirmation_product();client=APIClient();payload=self.pending_payload(client,variant)
        from .models import Order,Payment
        for method in ('bkash','nagad','bank'):
            response=client.post('/api/ecommerce/checkout/quote/',{**payload,'payment_method':method},format='json')
            self.assertEqual(response.status_code,200,response.data)
        payload.update(payment_method='bank',transaction_id='synthetic')
        response=client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(response.status_code,201,response.data)
        order=Order.objects.get();self.assertEqual(order.status,'confirmed');self.assertEqual(order.payment_status,'pending')
        self.assertEqual(Payment.objects.get().status,'pending')

    def test_unspecified_quantity_has_no_inventory_ceiling_and_checkout_is_idempotent(self):
        variant=self.confirmation_product();client=APIClient();payload=self.pending_payload(client,variant)
        cart=client.post('/api/ecommerce/cart/'+payload['cart_token']+'/',{'variant_id':variant.pk,
            'operation':'set','quantity':10000},format='json')
        self.assertEqual(cart.status_code,200,cart.data)
        response=client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(response.status_code,201,response.data);self.assertEqual(response.data['status'],'confirmed')
        repeat=client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(repeat.status_code,200,repeat.data);self.assertEqual(repeat.data['number'],response.data['number'])
        from .models import Order,InventoryMovement
        self.assertEqual(Order.objects.count(),1);self.assertEqual(Order.objects.get().items.get().quantity,10000)
        self.assertFalse(InventoryMovement.objects.exists());variant.refresh_from_db();self.assertEqual(variant.stock,0)

    def test_unspecified_supplier_quantity_does_not_bypass_another_products_approval(self):
        variant=self.confirmation_product();client=APIClient();payload=self.pending_payload(client,variant)
        other=Product.objects.create(name='Ordinary product',slug='ordinary',category=variant.product.category,status='active')
        other_variant=ProductVariant.objects.create(product=other,sku='ORDINARY',price='100',stock=5)
        response=client.post('/api/ecommerce/cart/'+payload['cart_token']+'/',{'variant_id':other_variant.pk,'quantity':1},format='json')
        self.assertEqual(response.status_code,200,response.data)
        quote=client.post('/api/ecommerce/checkout/quote/',payload,format='json')
        self.assertFalse(quote.data['stock_confirmation_required']);self.assertFalse(quote.data['order_auto_confirmed'])
        result=client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(result.status_code,201,result.data);self.assertEqual(result.data['status'],'pending')

    def test_unknown_quantity_wallet_order_uses_existing_debit_and_cancel_refund_rules(self):
        from cheradip.models import Customer,CustomerToken,WalletOperation
        user=Customer.objects.create_user(username='wallet-confirmation-test',password='synthetic',settings={'balance':1000000})
        CustomerToken.objects.create(customer=user,key='synthetic-confirmation-token')
        client=APIClient();client.credentials(HTTP_AUTHORIZATION='Bearer synthetic-confirmation-token')
        payload=self.pending_payload(client,self.confirmation_product());payload['payment_method']='wallet'
        quote=client.post('/api/ecommerce/checkout/quote/',payload,format='json');self.assertEqual(quote.status_code,200,quote.data)
        response=client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(response.status_code,201,response.data)
        from .models import Order
        from .order_service import change_order
        order=Order.objects.get();self.assertEqual(order.status,'confirmed')
        user.refresh_from_db();self.assertLess(user.settings['balance'],1000000)
        self.assertEqual(WalletOperation.objects.count(),1)
        change_order(order.pk,'cancelled')
        user.refresh_from_db();self.assertEqual(user.settings['balance'],1000000)
        self.assertEqual(WalletOperation.objects.count(),2)
        change_order(order.pk,'cancelled');self.assertEqual(WalletOperation.objects.count(),2)

    def test_finite_publication_resume_preserves_collection_and_does_not_repeat_completed_work(self):
        call_command('publish_fresh_supplier_catalogue',run_id=str(self.run.pk),apply=True,resume=True,stdout=StringIO())
        self.run.refresh_from_db();self.assertEqual(self.run.status,'completed')
        self.assertEqual(self.run.coverage['publication']['status'],'completed')
        self.assertEqual(self.run.coverage['publication']['last_source_id'],self.source.pk)
        with patch('ecommerce.management.commands.publish_fresh_supplier_catalogue.publish_source') as publish:
            call_command('publish_fresh_supplier_catalogue',run_id=str(self.run.pk),apply=True,resume=True,stdout=StringIO())
        publish.assert_not_called()

    def test_interrupted_database_publication_is_resumable_not_left_running(self):
        from django.db import OperationalError,connections
        from django.core.management.base import CommandError
        with patch('ecommerce.management.commands.publish_fresh_supplier_catalogue.publish_source',side_effect=OperationalError('Synthetic disconnect')), \
             patch.object(connections['ecommerce'],'close'):
            with self.assertRaises(CommandError):
                call_command('publish_fresh_supplier_catalogue',run_id=str(self.run.pk),apply=True,resume=True,stdout=StringIO())
        self.run.refresh_from_db()
        self.assertEqual(self.run.coverage['publication']['status'],'failed')
        self.assertEqual(self.run.coverage['publication']['last_source_id'],0)
        self.assertTrue(SupplierSourceProduct.objects.filter(pk=self.source.pk).exists())

    def test_historical_pending_stock_requests_still_require_staff_without_fabricating_stock(self):
        variant=self.confirmation_product();client=APIClient();payload=self.pending_payload(client,variant)
        response=client.post('/api/ecommerce/checkout/',payload,format='json')
        self.assertEqual(response.status_code,201,response.data)
        from .models import Order
        from cheradip.models import Customer
        from .order_service import change_order
        from .supplier_confirmation import pending
        order=Order.objects.get()
        # Existing requests retain their original recorded approval contract.
        order.status='pending';order.confirmed_at=None
        order.cost_snapshot={**order.cost_snapshot,'stock_confirmation':{'required':True,'product_ids':[variant.product_id]}}
        order.save()
        with self.assertRaises(ValueError):change_order(order.pk,'confirmed')
        customer=Customer.objects.create_user(username='confirmation-test',password='synthetic')
        with self.assertRaises(ValueError):change_order(order.pk,'confirmed',customer.pk)
        customer.is_staff=True;customer.save()
        change_order(order.pk,'confirmed',customer.pk)
        order.refresh_from_db();self.assertFalse(pending(order))
        self.assertEqual(order.cost_snapshot['stock_confirmation']['confirmed_by'],customer.pk)
        self.assertTrue(order.cost_snapshot['stock_confirmation']['confirmed_at'])
        variant.refresh_from_db();self.assertEqual(variant.stock,0)
        change_order(order.pk,'cancelled',customer.pk);variant.refresh_from_db();self.assertEqual(variant.stock,0)

    def test_unconfirmed_stock_and_unmapped_options_are_not_waived_by_pending_policy(self):
        self.confirmation_product()
        self.source.stock={'status':'unknown','quantity':None}
        with self.assertRaises(ValueError):source_variants(self.source)
        self.source.stock={'status':'in_stock','quantity':None};self.source.extra={'variant_inputs':[{'name':'size'}]}
        with self.assertRaises(ValueError):source_variants(self.source)

    def test_labelled_stock_connector_rechecks_own_product_and_preserves_unknown_quantity(self):
        from unittest.mock import Mock
        from .supplier_connectors import collect,ConnectorError
        from .supplier_service import snapshot_row
        variant=self.confirmation_product();supplier=variant.product.supplier_offer.supplier
        supplier.connector='labelled_stock';supplier.save()
        response=Mock(url=self.source.url,content=(
            '<meta charset="utf-8"><div class="product-details-page"><input name="product_id" value="P1">'
            '<div id="descriptionCopy">Original complete description</div>প্রাইস: 101 স্টক: আছে</div>').encode())
        with patch('ecommerce.supplier_connectors.decrypt',return_value={'username':'synthetic','password':'synthetic'}), \
             patch('ecommerce.supplier_source_clients.SourceClient') as factory:
            client=factory.return_value;client.site='shopbase';client.request.return_value=response
            rows,stats=collect(supplier)
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['quantity']);self.assertEqual(rows[0]['source_price'],'101.00')
        self.assertEqual(stats['supplier_orders'],0)
        snapshot_row(supplier,rows[0],update=True)
        variant.refresh_from_db();self.assertEqual(variant.stock,0);self.assertTrue(variant.allow_backorder)
        source=type(self.source).objects.get(pk=self.source.pk)
        self.assertEqual(source.observed_at,self.source.observed_at)
        self.assertIn('price_stock_checked_at',source.extra)
        self.assertEqual(source.description,self.source.description)
        response.content=response.content.replace(b'value="P1"',b'value="OTHER"')
        with patch('ecommerce.supplier_connectors.decrypt',return_value={'username':'synthetic','password':'synthetic'}), \
             patch('ecommerce.supplier_source_clients.SourceClient') as factory:
            factory.return_value.site='shopbase';factory.return_value.request.return_value=response
            with self.assertRaises(ConnectorError):collect(supplier)

    def test_new_labelled_stock_refresh_cannot_be_overwritten_by_older_offer(self):
        from .supplier_label_stock import remember_stock
        self.confirmation_product()
        remember_stock(self.source,{'prices':{'reseller_price':{'amount':'102'}},'stock':{'status':'in_stock'}})
        publish_source(self.source.pk)
        offer=SupplierOffer.objects.get();self.assertEqual(offer.source_price,Decimal('102'))
        self.assertIsNone(offer.quantity)
        self.assertGreater(offer.observed_at,self.source.observed_at)

    def test_dropify_stock_compares_only_own_heading_not_description_headings(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        from .supplier_label_stock import read_stock
        source=SimpleNamespace(supplier_id=7,title='Own product',external_id='own',url='https://www.dropifybd.com/product/own')
        page='''<h1 class="pd-name">Own product</h1><div class="pd-image-col"><img src="/own.jpg"></div>
        <div class="pd-info-col"><div class="pd-price-item-value wholesale">100</div>
        <div class="pd-price-item-value stock-in">In Stock</div></div>
        <div class="pd-desc-content"><h1>Longer marketing heading inside description</h1>Full description</div>'''
        client=Mock(site='dropify');client.request.return_value=Mock(url=source.url,content=page.encode())
        data=read_stock(client,source)
        self.assertEqual(data['prices']['wholesale']['amount'],'100.00')
        self.assertEqual(data['stock']['status'],'in_stock')
        source.title='A different product'
        with self.assertRaises(ValueError):read_stock(client,source)

    def test_dropify_buying_and_minimum_selling_prices_are_kept_separate(self):
        supplier=Supplier.objects.create(pk=7,name='Dropify test',website='https://www.dropifybd.com',enabled=True,terms_confirmed=True)
        self.source.supplier=supplier;self.source.variants=[];self.source.extra={'account_price_verified':True}
        self.source.prices={'wholesale':{'amount':'100'},'minimum_selling_price':{'amount':'250'}}
        self.source.stock={'status':'in_stock','quantity':None};self.source.save()
        publish_source(self.source.pk);variant=ProductVariant.objects.get()
        self.assertEqual(variant.cost_price,Decimal('100'));self.assertEqual(variant.price,Decimal('252'))
        product=variant.product;rule=product.attributes['_retail_pricing'][str(variant.pk)]
        rule.update(base_price='150',sale_price='150',regular_price='167',applied_price='150')
        product.status='archived';product.save();variant.price=Decimal('150');variant.save()
        publish_source(self.source.pk);variant.refresh_from_db();self.assertEqual(variant.price,Decimal('252'))
        variant.price=Decimal('175');variant.save()  # An explicit staff change stays held, not overwritten.
        publish_source(self.source.pk);variant.refresh_from_db();self.assertEqual(variant.price,Decimal('175'))
        self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],0)
        self.source.extra={}
        with self.assertRaises(ValueError):source_variants(self.source)

    def test_out_of_stock_unknown_variant_stock_and_stale_checks_never_become_orderable(self):
        self.source.variants[0]['stockQuantity']=0;self.source.save()
        self.assertEqual(publish_source(self.source.pk),{'held':1})
        self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],0)
        self.source.variants[0]['stockQuantity']=None;self.source.save()
        with self.assertRaises(ValueError): source_variants(self.source)
        self.source.observed_at=timezone.now()-timedelta(hours=25);self.source.save()
        self.source.variants[0]['stockQuantity']=3;self.source.save()
        with self.assertRaises(ValueError):publish_source(self.source.pk)

    def test_idempotent_refresh_preserves_staff_content_and_selling_price(self):
        publish_source(self.source.pk)
        offer=SupplierOffer.objects.get();product=offer.imported_product;variant=product.variants.get()
        Product.objects.filter(pk=product.pk).update(description='Staff edited content',name='Edited title')
        variant.price=Decimal('199');variant.save()
        publish_source(self.source.pk)
        product.refresh_from_db();variant.refresh_from_db()
        self.assertEqual(product.description,'Staff edited content');self.assertEqual(product.name,'Edited title')
        self.assertEqual(variant.price,Decimal('199'));self.assertEqual(Product.objects.count(),1)

    def test_missing_or_inaccessible_photos_do_not_publish(self):
        self.photo.stop()
        with patch('ecommerce.supplier_source_publish.verify_photo',side_effect=ValueError('Source image unavailable')):
            with self.assertRaises(ValueError):publish_source(self.source.pk)
        self.assertFalse(Product.objects.exists())
        self.photo.start()

    def test_broken_additional_gallery_entry_is_retained_privately_not_a_logo_substitute(self):
        from .models import SupplierSourceMedia
        extra=SupplierSourceMedia.objects.create(product=self.source,media_key='b'*64,kind='image',role='gallery',
            original_url='https://cdn.businesskoro.com/products/broken.jpg',position=1,last_seen_at=timezone.now(),last_run=self.run)
        def verify(media):
            if media.pk == extra.pk: raise ValueError('Original extra image unavailable')
            media.stored_url='/manage/media/supplier_products/synthetic.jpg';media.metadata={'verified_image':True};media.save();return media
        with patch('ecommerce.supplier_source_publish.verify_photo',side_effect=verify):
            self.assertEqual(publish_source(self.source.pk),{'published':1})
        extra.refresh_from_db();self.assertFalse(extra.metadata['verified_image'])
        detail=APIClient().get('/api/ecommerce/products/'+Product.objects.get().slug+'/').data
        self.assertEqual(len(detail['images']),1)
        self.assertTrue(SupplierSourceMedia.objects.filter(pk=extra.pk).exists())

    def test_explicit_repricing_does_not_compound_and_private_rule_is_not_public(self):
        publish_source(self.source.pk)
        variant = ProductVariant.objects.get()
        from .pricing import retail_prices
        original = Decimal(variant.product.attributes['_retail_pricing'][str(variant.pk)]['sale_price'])
        initial = variant.price
        call_command('set_supplier_retail_prices', mode='reserve', apply=True, stdout=StringIO())
        variant.refresh_from_db(); reserved = variant.price
        self.assertGreater(reserved, original); self.assertEqual(initial, original)
        self.assertEqual(reserved, reserved.to_integral_value())
        call_command('set_supplier_retail_prices', mode='reserve', apply=True, stdout=StringIO())
        variant.refresh_from_db(); self.assertEqual(variant.price, reserved)
        call_command('set_supplier_retail_prices', mode='sale', apply=True, stdout=StringIO())
        variant.refresh_from_db()
        self.assertEqual(variant.price, original)
        self.assertEqual(variant.compare_at_price, reserved)
        detail = APIClient().get('/api/ecommerce/products/'+variant.product.slug+'/').data
        self.assertNotIn('_retail_pricing', detail['attributes'])
        self.assertNotIn('supplier_publication_ready', detail['attributes'])
        self.assertFalse(__import__('ecommerce.models',fromlist=['Order']).Order.objects.exists())

    def test_reference_rounding_migration_applies_discount_after_rounding(self):
        publish_source(self.source.pk)
        variant=ProductVariant.objects.get();product=variant.product
        variant.price=Decimal('830');variant.compare_at_price=Decimal('920')
        variant.save(update_fields=['price','compare_at_price'])
        rules={**product.attributes.get('_retail_pricing',{}),str(variant.pk):{
            'base_price':'829.14','sale_price':'830','regular_price':'920','discount_percent':'10',
            'rounding':'nearest_ten_remainder_4_rounds_up','version':2,'mode':'sale','applied_price':'830'}}
        product.attributes={**product.attributes,'_retail_pricing':rules};product.save(update_fields=['attributes'])

        call_command('migrate_supplier_reference_rounding',stdout=StringIO())
        variant.refresh_from_db();self.assertEqual(variant.compare_at_price,Decimal('920'))
        self.assertEqual(variant.price,Decimal('830'))
        call_command('migrate_supplier_reference_rounding',apply=True,stdout=StringIO())
        variant.refresh_from_db();product.refresh_from_db()
        self.assertEqual(variant.compare_at_price,Decimal('920'))
        self.assertEqual(variant.price,Decimal('828'))
        self.assertEqual(product.attributes['_retail_pricing'][str(variant.pk)]['version'],3)
        self.assertEqual(product.attributes['_retail_pricing'][str(variant.pk)]['applied_price'],'828')
        call_command('migrate_supplier_reference_rounding',apply=True,stdout=StringIO())
        variant.refresh_from_db();self.assertEqual(variant.price,Decimal('828'))

        # An intervening manual price change must not be discounted a second time.
        product.attributes['_retail_pricing'][str(variant.pk)]['version']=2
        product.save(update_fields=['attributes'])
        variant.price=Decimal('835');variant.save(update_fields=['price'])
        call_command('migrate_supplier_reference_rounding',apply=True,stdout=StringIO())
        variant.refresh_from_db();self.assertEqual(variant.price,Decimal('835'))

    def test_old_imported_draft_gets_owner_rounding_once_before_republication(self):
        publish_source(self.source.pk)
        product=Product.objects.get();variant=product.variants.get()
        product.attributes.pop('_retail_pricing');product.status='archived';product.save()
        variant.price=Decimal('729.60');variant.save()
        publish_source(self.source.pk)
        variant.refresh_from_db();product.refresh_from_db()
        self.assertEqual(variant.price,Decimal('729'))
        self.assertEqual(variant.compare_at_price,Decimal('810'))
        self.assertEqual(product.attributes['_retail_pricing'][str(variant.pk)]['base_price'],'729.60')
        publish_source(self.source.pk);variant.refresh_from_db()
        self.assertEqual(variant.price,Decimal('729'))

    def test_simple_reseller_product_uses_reseller_cost_never_retail_or_aggregate_options(self):
        supplier=Supplier.objects.create(pk=8,name='Reseller test',website='https://resellkori.com',enabled=True,terms_confirmed=True)
        self.source.supplier=supplier
        self.source.variants=[]
        self.source.prices={'market':{'amount':'999'},'reseller':{'amount':'100'}}
        self.source.stock={'quantity':5}
        self.source.raw_data={'store_api_product':{'type':'simple','is_in_stock':True}}
        rows=source_variants(self.source)
        self.assertEqual(rows[0]['cost'],Decimal('100'));self.assertEqual(rows[0]['quantity'],5)
        self.source.variants=[{'id':'option-unmapped'}]
        with self.assertRaises(ValueError):source_variants(self.source)

    def test_dropshipping_uses_account_cost_and_only_exact_positive_simple_stock(self):
        supplier=Supplier.objects.create(pk=9,name='Dropshipping test',website='https://www.dropshipping.com.bd',enabled=True,terms_confirmed=True)
        self.source.supplier=supplier;self.source.variants=[]
        self.source.prices={'sale_price':{'amount':'330'},'reselling_price':{'amount':'690'}}
        self.source.extra={'account_authenticated':True}
        self.source.stock={'quantity':2,'status':'in_stock','status_code':1}
        self.assertEqual(source_variants(self.source)[0]['cost'],Decimal('330'))
        self.source.stock['quantity']=-2;self.source.stock['status']='out_of_stock'
        with self.assertRaises(ValueError):source_variants(self.source)
        self.source.stock={'quantity':2,'status':'in_stock','status_code':1}
        self.source.variants=[{'name':'size','options':[{'value':'L'}]}]
        with self.assertRaises(ValueError):source_variants(self.source)

    def test_restricted_supplier_never_downloads_photos_or_publishes(self):
        self.supplier.enabled=False;self.supplier.save()
        with patch('ecommerce.supplier_source_publish.verify_photo') as photo:
            with self.assertRaises(ValueError):publish_source(self.source.pk)
        photo.assert_not_called();self.assertFalse(Product.objects.exists())

    def test_dropshipping_stock_refresh_reads_tracked_identity_not_other_catalogue_rows(self):
        from .supplier_connectors import collect
        supplier=Supplier.objects.create(pk=9,name='Dropshipping test',website='https://www.dropshipping.com.bd',
            connector='dropshipping_bd',enabled=True,terms_confirmed=True)
        self.source.supplier=supplier;self.source.variants=[]
        self.source.prices={'sale_price':{'amount':'100'}}
        self.source.extra={'account_authenticated':True}
        self.source.stock={'quantity':3,'status':'in_stock','status_code':1};self.source.save()
        publish_source(self.source.pk)
        offer=SupplierOffer.objects.get();offer.external_id='legacy-url-id';offer.title='Older short title';offer.save()
        with patch('ecommerce.supplier_connectors.decrypt',return_value={'username':'synthetic','password':'synthetic'}), \
             patch('ecommerce.supplier_source_clients.SourceClient') as factory:
            client=factory.return_value;client.origin='https://www.dropshipping.com.bd'
            catalog=__import__('unittest.mock',fromlist=['Mock']).Mock()
            catalog.json.return_value={'products':{'total':2,'last_page':1,'data':[
                {'id':self.source.external_id,'name':self.source.title,'sale_price':101,'reselling_price':200,'status':1},
                {'id':'not-tracked','name':'Other','sale_price':1,'status':1}]}}
            detail=__import__('unittest.mock',fromlist=['Mock']).Mock()
            detail.content=f'<input id="single_page_product_id" value="{self.source.external_id}"><input id="product_stock" value="2">'.encode()
            client.request.side_effect=[catalog,detail]
            rows,stats=collect(supplier)
        self.assertEqual(client.request.call_count,2)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source_price'],'101')
        self.assertEqual(rows[0]['quantity'],2);self.assertEqual(stats['imports'],0)
        self.assertEqual(rows[0]['external_id'],'legacy-url-id')
        from .supplier_service import snapshot_row
        self.assertEqual(snapshot_row(supplier,rows[0],update=True),'updated')
        variant=ProductVariant.objects.get();self.assertEqual(variant.stock,2);self.assertEqual(variant.cost_price,Decimal('101'))
        self.assertEqual(SupplierOffer.objects.count(),1)

    def test_account_stock_connector_updates_only_tracked_rows_without_content_or_order_submission(self):
        from .supplier_connectors import collect
        from .supplier_service import snapshot_row
        supplier=Supplier.objects.create(pk=3,name='Uddoog test',website='https://dropshop.com.bd',
            connector='uddoog',enabled=True,terms_confirmed=True)
        self.source.supplier=supplier;self.source.variants=[]
        self.source.prices={'base_price':{'amount':'100'}}
        self.source.stock={'quantity':3,'status':'active'}
        self.source.extra={'account_authenticated':True};self.source.save()
        publish_source(self.source.pk)
        variant=ProductVariant.objects.get();price=variant.price
        with patch('ecommerce.supplier_connectors.decrypt',return_value={'username':'synthetic','password':'synthetic'}), \
             patch('ecommerce.supplier_source_clients.SourceClient') as factory:
            factory.return_value.origin='https://dropshop.com.bd'
            factory.return_value.request.return_value.json.return_value={'data':{'total':2,'items':[
                {'id':'P1','name':self.source.title,'base_price':101,'stock':2,'status':'active'},
                {'id':'not-tracked','name':'Another','base_price':10,'stock':50,'status':'active'}]}}
            rows,stats=collect(supplier)
        self.assertEqual(len(rows),1);self.assertEqual(stats['content_downloads'],0)
        self.assertEqual(SupplierOffer.objects.count(),1)
        snapshot_row(supplier,rows[0],update=True)
        variant.refresh_from_db();self.assertEqual(variant.stock,2)
        self.assertEqual(variant.price,price);self.assertEqual(variant.cost_price,Decimal('101'))

    def test_nightly_exact_variant_refresh_preserves_enriched_identity_images_and_selling_price(self):
        from .supplier_service import snapshot_row
        publish_source(self.source.pk)
        offer=SupplierOffer.objects.get();product=offer.imported_product;variant=product.variants.get()
        offer.identity['specifications']['fabric']='Staff researched fabric';offer.save()
        price=variant.price;photos=list(product.images.values_list('url',flat=True))
        row={'external_id':offer.external_id,'variant_id':offer.variant_id,'vendor_id':offer.vendor_id,'warehouse_id':offer.warehouse_id,
             'title':self.source.title,'url':offer.url,'identity':{'specifications':{'color':'Red','size':'L'}},'source_price':'101.00',
             'availability':'in_stock','quantity':2,'observed_at':timezone.now().isoformat()}
        self.assertEqual(snapshot_row(self.supplier,row,update=True),'updated')
        offer.refresh_from_db();variant.refresh_from_db()
        self.assertEqual(variant.price,price);self.assertEqual(variant.stock,2);self.assertEqual(variant.cost_price,Decimal('101'))
        self.assertIn('fabric',offer.identity['specifications']);self.assertEqual(list(product.images.values_list('url',flat=True)),photos)
        row.update(quantity=0,availability='out_of_stock',observed_at=timezone.now().isoformat())
        snapshot_row(self.supplier,row,update=True)
        self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],0)
        row.update(quantity=2,availability='in_stock',observed_at=timezone.now().isoformat())
        snapshot_row(self.supplier,row,update=True)
        self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],1)
        row.update(title='Different product reused identifier',observed_at=timezone.now().isoformat())
        self.assertEqual(snapshot_row(self.supplier,row,update=True),'conflict')
        self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],0)

    def test_content_release_does_not_undo_newer_stock_check_or_restore_sold_out_item(self):
        from .supplier_service import snapshot_row
        publish_source(self.source.pk)
        offer=SupplierOffer.objects.get()
        row={'external_id':offer.external_id,'variant_id':offer.variant_id,'vendor_id':offer.vendor_id,
             'warehouse_id':offer.warehouse_id,'title':offer.title,'url':offer.url,'identity':deepcopy(offer.identity),
             'source_price':'101.00','availability':'out_of_stock','quantity':0,'observed_at':timezone.now().isoformat()}
        snapshot_row(self.supplier,row,update=True)
        offer.refresh_from_db();newer=offer.observed_at
        publish_source(self.source.pk)
        offer.refresh_from_db();variant=ProductVariant.objects.get()
        self.assertEqual(offer.observed_at,newer);self.assertEqual(offer.source_price,Decimal('101'))
        self.assertEqual(variant.stock,0);self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],0)

    def test_new_full_source_sold_out_result_hides_old_offer_until_a_newer_real_stock_check(self):
        from .supplier_service import snapshot_row
        publish_source(self.source.pk);offer=SupplierOffer.objects.get()
        self.source.stock={'quantity':0,'status':'out_of_stock'};self.source.observed_at=timezone.now();self.source.save()
        self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],0)
        row={'external_id':offer.external_id,'variant_id':offer.variant_id,'vendor_id':offer.vendor_id,
            'warehouse_id':offer.warehouse_id,'title':offer.title,'url':offer.url,'identity':deepcopy(offer.identity),
            'source_price':'101','availability':'in_stock','quantity':2,'observed_at':timezone.now().isoformat()}
        snapshot_row(self.supplier,row,update=True)
        self.assertEqual(APIClient().get('/api/ecommerce/products/').data['count'],1)

    def test_incremental_source_transfer_preserves_original_dates_and_does_not_copy_shop_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.gz'
            call_command('transfer_supplier_sources',run_id=str(self.run.pk),export_path=str(path),stdout=StringIO())
            before=self.source.observed_at
            call_command('transfer_supplier_sources',import_path=str(path),stdout=StringIO())
            self.source.refresh_from_db()
            self.assertEqual(self.source.observed_at,before)
            self.assertFalse(Product.objects.exists());self.assertFalse(SupplierOffer.objects.exists())

    def test_bounded_transfer_parts_are_checked_and_preserve_existing_image_verification(self):
        import json
        from django.core.management.base import CommandError
        publish_source(self.source.pk)
        self.run.status='running';self.run.save()
        for n in range(2,102):
            save_record(self.run.pk,{**deepcopy(self.record),'external_id':str(n)})
        self.run.refresh_from_db();self.run.status='completed';self.run.save()
        with tempfile.TemporaryDirectory() as directory:
            call_command('transfer_supplier_sources',run_id=str(self.run.pk),export_directory=directory,stdout=StringIO())
            manifest_path=Path(directory)/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            self.assertEqual(len(manifest['parts']),2)
            self.assertTrue(all(p['products']<=100 for p in manifest['parts']))
            call_command('transfer_supplier_sources',import_directory=directory,stdout=StringIO())
            self.assertEqual(SupplierSourceProduct.objects.count(),101)
            self.assertTrue(self.source.media.get().metadata['verified_image'])
            self.assertEqual(Product.objects.count(),1)
            self.run.refresh_from_db();self.assertEqual(self.run.status,'completed')
            manifest['parts'][0]['file']='../outside.json.gz'
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(CommandError):
                call_command('transfer_supplier_sources',import_directory=directory,stdout=StringIO())
