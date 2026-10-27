from django.test import TransactionTestCase
from rest_framework.test import APIClient
from . import test_suppliers as fixtures
from .models import Product, SupplierOffer
from .supplier_service import policy
from .supplier_media import safe_images


class CatalogueTests(TransactionTestCase):
    databases={'default','ecommerce'}
    setUp=fixtures.SupplierTests.setUp
    row=fixtures.SupplierTests.row
    def offer(self):
        from .models import SupplierRecollectionRun, SupplierSourceProduct
        from .supplier_recollection import save_record
        offer = fixtures.SupplierTests.offer(self)
        run = SupplierRecollectionRun.objects.create(supplier=self.supplier, mode='full', status='running')
        save_record(run.pk, {'external_id': offer.external_id, 'title': offer.title, 'url': offer.url,
            'description': 'Complete original supplier content', 'media': [{'url': 'https://supplier.example/own.jpg', 'role': 'main'}]})
        offer.source_product = SupplierSourceProduct.objects.get(last_run=run)
        offer.source_product.media.update(metadata={'verified_image': True})
        offer.preview_images = ['https://supplier.example/own.jpg']
        offer.save(using='ecommerce')
        return offer

    def mode(self,mode='all'):
        preview=self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':mode},format='json')
        self.assertEqual(preview.status_code,200,preview.data)
        result=self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':mode,'preview':False,'preview_token':preview.data['preview_token']},format='json')
        self.assertEqual(result.status_code,200,result.data)
        return result

    def test_all_imports_without_research_and_filtered_archives_without_deleting(self):
        from .supplier_service import run_jobs
        offer=self.offer(); original=(offer.state,offer.source_price,offer.observed_at)
        result=self.mode('all'); self.assertEqual(len(result.data['jobs']),1)
        run_jobs(); offer.refresh_from_db()
        self.assertEqual((offer.state,offer.source_price,offer.observed_at),original)
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'],1)
        product=offer.imported_product
        detail=self.client.get('/api/ecommerce/products/'+product.slug+'/').data
        self.assertEqual(detail['fulfilment_mode'],'manual_supplier_catalogue')
        self.assertNotIn('supplier_reference',detail)
        self.assertNotIn(offer.url,str(detail))
        self.mode('filtered')
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'],0)
        self.assertEqual(Product.objects.using('ecommerce').count(),1)
        self.mode('all'); self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'],1)
        # No residual enquiry-preview route can expose unverified records.
        self.assertEqual(self.client.get('/api/ecommerce/catalogue/').status_code,404)
        self.assertEqual(self.client.post('/api/ecommerce/catalogue/enquiries/',{},format='json').status_code,404)

    def test_missing_price_is_not_a_free_order_and_unknown_stock_is_not_invented(self):
        from .supplier_service import run_jobs
        offer=self.offer(); offer.source_price=None; offer.quantity=None; offer.availability='unconfirmed'; offer.save(using='ecommerce')
        self.mode(); run_jobs(); offer.refresh_from_db()
        self.assertEqual(offer.imported_product.variants.count(),0)
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'],0)
        other=SupplierOffer.objects.using('ecommerce').create(supplier=self.supplier,external_id='unknown-stock',
            title='Known price',source_price=100,url='https://supplier.example/known')
        self.mode(); run_jobs(); other.refresh_from_db()
        variant=other.imported_product.variants.get()
        self.assertFalse(variant.allow_backorder); self.assertEqual(variant.stock,0)
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'],0)

    def test_bootstrap_export_contains_valid_fields_and_no_credentials(self):
        import gzip, json, tempfile
        from pathlib import Path
        from django.core.management import call_command
        from django.core import serializers
        from io import StringIO
        from .models import SupplierEvidence
        offer=self.offer()
        fixtures.SupplierTests.evidence(self,offer,'independent','150')
        self.supplier.credentials_ciphertext='SECRET-NEVER-EXPORT'; self.supplier.save(using='ecommerce')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'catalogue.json.gz'
            call_command('transfer_supplier_catalogue',export_path=str(path),stdout=StringIO())
            with gzip.open(path,'rt',encoding='utf-8') as stream: payload=json.load(stream)
            self.assertNotIn('SECRET-NEVER-EXPORT',json.dumps(payload))
            records=list(serializers.deserialize('json',json.dumps(payload['records']),using='ecommerce'))
            self.assertTrue(records)
            for row in records:
                if isinstance(row.object,SupplierEvidence): self.assertIsNotNone(row.object.actor_id)

    def test_manual_request_checkout_and_cancel_never_invent_inventory_or_leak_source(self):
        from .supplier_service import run_jobs
        from .models import Order, InventoryMovement
        from .order_service import change_order
        from .serializers import OrderSerializer, CustomerOrderSerializer
        offer=self.offer()
        self.mode(); run_jobs(); offer.refresh_from_db(); variant=offer.imported_product.variants.get()
        cart=self.client.post('/api/ecommerce/cart/',{'variant_id':variant.pk,'quantity':1},format='json')
        self.assertEqual(cart.status_code,200,cart.data)
        data={'cart_token':cart.data['token'],'customer_name':'Test only','phone':'01710000000','email':'test@example.com',
            'shipping_address':{'country_code':'BD','district':'Dhaka','thana':'Savar','address':'Test road'},'payment_method':'cod'}
        quote=self.client.post('/api/ecommerce/checkout/quote/',data,format='json')
        self.assertEqual(quote.status_code,200,quote.data)
        checkout=self.client.post('/api/ecommerce/checkout/',{**data,'quoted_total':str(quote.data['grand_total'])},format='json')
        self.assertEqual(checkout.status_code,201,checkout.data)
        order=Order.objects.using('ecommerce').get()
        self.assertEqual(order.status,'pending'); self.assertEqual(order.payment_status,'unpaid')
        self.assertEqual(OrderSerializer(order).data['items'][0]['supplier_reference'],offer.url)
        self.assertNotIn('supplier_reference',CustomerOrderSerializer(order).data['items'][0])
        change_order(order.pk,'confirmed',self.user.pk)
        change_order(order.pk,'cancelled',self.user.pk)
        variant.refresh_from_db(); self.assertEqual(variant.stock,20)
        self.assertTrue(InventoryMovement.objects.using('ecommerce').filter(variant=variant,reason='sale').exists())

    def test_photo_provenance_and_unconfirmed_stock_hide_but_stale_positive_check_remains_visible(self):
        from .supplier_service import run_jobs
        from .models import ProductImage
        from django.utils import timezone
        from datetime import timedelta
        offer = self.offer(); self.mode(); run_jobs(); offer.refresh_from_db()
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'], 1)
        offer.availability='unconfirmed'; offer.save()
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'], 0)
        variant = offer.imported_product.variants.get()
        self.assertEqual(self.client.post('/api/ecommerce/cart/', {'variant_id':variant.pk, 'quantity':1}, format='json').status_code,409)
        offer.availability='in_stock'; offer.observed_at=timezone.now()-timedelta(hours=25); offer.save()
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'], 1)
        offer.observed_at=timezone.now(); offer.save()
        ProductImage.objects.filter(product=offer.imported_product).update(source_media=None,url='https://supplier.example/logo.png')
        self.assertEqual(self.client.get('/api/ecommerce/products/').data['count'], 0)

    def test_storefront_stock_responses_cannot_be_reused_from_browser_or_proxy_cache(self):
        from .supplier_service import run_jobs
        offer=self.offer();self.mode();run_jobs();offer.refresh_from_db()
        for path in ('/api/ecommerce/products/', '/api/ecommerce/products/'+offer.imported_product.slug+'/', '/api/ecommerce/categories/'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn('no-store',response['Cache-Control'])
            self.assertIn('must-revalidate',response['Cache-Control'])

    def test_empty_target_bootstrap_reencrypts_credentials_without_plaintext_export(self):
        import gzip, json, tempfile
        from pathlib import Path
        from io import StringIO
        from django.test import override_settings
        from django.core.management import call_command
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from .models import (Supplier, SupplierJob, SupplierAudit, Category, SupplierPolicy,
                             SupplierRecollectionRun, SupplierSourceProduct, SupplierSourceMedia, SupplierRecollectionItem)
        from .supplier_crypto import encrypt, decrypt
        offer=self.offer()
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        with tempfile.TemporaryDirectory() as folder, override_settings(COMMERCE_SUPPLIER_KEY=Fernet.generate_key().decode()):
            public=Path(folder)/'public.pem'; private=Path(folder)/'private.pem'; bundle=Path(folder)/'catalogue.gz'
            public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
            private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            self.supplier.credentials_ciphertext=encrypt({'api_key':'test-only-not-a-real-key'}); self.supplier.save(using='ecommerce')
            call_command('transfer_supplier_catalogue',export_path=str(bundle),recipient_public_key=str(public),stdout=StringIO())
            with gzip.open(bundle,'rt',encoding='utf-8') as stream: payload=json.load(stream)
            self.assertNotIn('test-only-not-a-real-key',json.dumps(payload))
            # These are disposable SQLite test records, never a business DB.
            SupplierAudit.objects.using('ecommerce').all().delete(); SupplierJob.objects.using('ecommerce').all().delete()
            SupplierOffer.objects.using('ecommerce').all().delete()
            SupplierRecollectionItem.objects.all().delete(); SupplierSourceMedia.objects.all().delete()
            SupplierSourceProduct.objects.all().delete(); SupplierRecollectionRun.objects.all().delete()
            Supplier.objects.using('ecommerce').all().delete()
            Category.objects.using('ecommerce').all().delete(); SupplierPolicy.objects.using('ecommerce').all().delete()
            call_command('transfer_supplier_catalogue',import_path=str(bundle),recipient_private_key=str(private),stdout=StringIO())
            self.assertEqual(decrypt(Supplier.objects.using('ecommerce').get(pk=self.supplier.pk)),{'api_key':'test-only-not-a-real-key'})
            self.assertEqual(SupplierOffer.objects.using('ecommerce').get(pk=offer.pk).url,offer.url)

    def test_ordinary_inventory_and_permanent_exclusions_are_unchanged(self):
        offer=self.offer(); offer.state='excluded'; offer.excluded_reason='Permanent manual exclusion'; offer.save(using='ecommerce')
        own=Product.objects.using('ecommerce').create(name='Own inventory',slug='own',category=self.category,status='active')
        revision=policy().revision
        self.mode(); self.mode('filtered')
        offer.refresh_from_db(); own.refresh_from_db()
        self.assertEqual(offer.state,'excluded'); self.assertEqual(own.status,'active')
        self.assertEqual(policy().revision,revision)

    def test_changes_require_permission_and_fresh_signed_preview(self):
        self.assertIn(APIClient().post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':'all'},format='json').status_code,(401,403))
        result=self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':'all'},format='json')
        self.assertEqual(policy().catalogue_mode,'filtered')
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':'all','preview':False},format='json').status_code,400)
        self.mode()
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':'all','preview':False,'preview_token':result.data['preview_token']},format='json').status_code,400)
        self.user.is_superuser=False; self.user.save()
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':'all'},format='json').status_code,403)

    def test_old_preview_rule_confirmation_is_invalid(self):
        from django.core import signing
        token=signing.dumps(dict(actor=self.user.pk,mode='all',revision=policy().catalogue_revision),salt='supplier-catalogue-mode')
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-catalogue-mode/',{'mode':'all','preview':False,'preview_token':token},format='json').status_code,400)

    def test_image_references_reject_secrets_and_private_networks(self):
        self.assertEqual(safe_images(['https://supplier.example/1.jpg','https://supplier.example/1.jpg','https://supplier.example/a?token=secret','https://localhost/a','https://127.0.0.1/a','https://private.lan/a','data:image/png;base64,abc','http://supplier.example/a','https://supplier.example:bad/a']),['https://supplier.example/1.jpg'])

    def test_collection_fills_missing_photo_references_but_nightly_does_not(self):
        from .supplier_service import snapshot_row
        from django.utils import timezone
        offer=self.offer(); row=self.row(); row['preview_images']=['https://supplier.example/1.jpg']
        offer.preview_images=[]; offer.save()
        self.assertEqual(snapshot_row(self.supplier,row),'existing')
        offer.refresh_from_db(); self.assertEqual(offer.preview_images,row['preview_images'])
        row['preview_images']=['https://supplier.example/2.jpg']; row['observed_at']=timezone.now().isoformat()
        self.assertEqual(snapshot_row(self.supplier,row,update=True),'updated')
        offer.refresh_from_db(); self.assertEqual(offer.preview_images,['https://supplier.example/1.jpg'])
