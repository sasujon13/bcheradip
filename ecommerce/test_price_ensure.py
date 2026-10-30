import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from cheradip.models import Customer, CustomerToken

from .price_ensure import SAMPLES, check_gold_html, extract_buying_price
from .supplier_source_parsers import html_product


class GoldHtmlExtractionTests(SimpleTestCase):
    def test_owner_html_snippets_extract_the_labelled_buying_prices(self):
        rows = check_gold_html()
        self.assertTrue(all(row['ok'] for row in rows), rows)
        self.assertEqual([row['extracted'] for row in rows], [s['expected'] for s in SAMPLES])

    def test_dropify_wholesale_is_not_the_suggested_figure(self):
        html = '''<div class="pd-price-item"><div class="pd-price-item-label">Suggested Price</div>
            <div class="pd-price-item-value suggested">৳1,850</div></div>
            <div class="pd-price-item"><div class="pd-price-item-label">Wholesale Price</div>
            <div class="pd-price-item-value wholesale">৳1,150</div></div>'''
        self.assertEqual(extract_buying_price('dropify', html), ('1150.00', 'Wholesale Price'))

    def test_resellkori_full_page_reads_the_reselling_price_button(self):
        page = '''<html><body><h1>Silver Crest</h1><div class="single-product-content">
            <div class="woocommerce-product-gallery__wrapper"></div>
            <div class="summary"><a class="reselling-price-btn">Reseller Price: 692৳</a>
            <div>Market Price: 999৳</div></div>
            <select name="rating"><option value="5">Perfect</option></select>
            <div id="tab-description">Original description</div></div></body></html>'''
        record = html_product('resellkori', SAMPLES[0]['url'], page, title='Silver Crest')
        self.assertEqual(record['prices']['reseller']['amount'], '692.00')
        self.assertEqual(record['variants'], [])

    def test_ensure_prices_gold_pass_without_live_logins(self):
        rows = check_gold_html()
        self.assertTrue(all(row['ok'] for row in rows), rows)

    def test_selfshop_reads_labelled_price_instead_of_reseller_or_related_prices(self):
        page='''<h1>Shirt</h1><div class="text-gray-700">99</div>
            <p>Reseller Price: 650</p><div><span>Price :</span><div>715.00</div></div>
            <section><h3>Related item</h3><div class="text-gray-700">484.00</div></section>'''
        self.assertEqual(extract_buying_price('selfshop',page),('715.00','Price'))
        self.assertEqual(extract_buying_price('selfshop',page.replace('715.00','799.00')),('799.00','Price'))

    def test_selfshop_ignores_struck_reference_price(self):
        page='''<div><span>Price :</span><div>
            <span class="text-gray-400 line-through">1,500.00</span>
            <div class="text-pink-600 font-bold">1,392.00</div>
        </div></div>'''
        self.assertEqual(extract_buying_price('selfshop',page),('1392.00','Price'))

    def test_dropshipping_duplicate_dom_ids_do_not_select_retail_or_profit(self):
        page='''<span id="variant_wise_price">সম্ভাব্য বিক্রয় মূল্যঃ 390 TK</span>
            <span id="variant_wise_price">আপনার প্রফিটঃ 240 TK</span>
            <span id="variant_wise_price">ড্রপশিপার প্রাইজঃ 150 TK</span>'''
        self.assertEqual(extract_buying_price('dropshipping',page),('150.00','ড্রপশিপার প্রাইজ'))


class EnsurePricesApiTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='price-staff', password='test-only', fullName='Price Staff')
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        CustomerToken.objects.create(key='price-test-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer price-test-token', HTTP_X_FORWARDED_PROTO='https')

    def test_staff_queues_current_browser_check_without_a_gold_mode(self):
        with patch('ecommerce.price_ensure.queue_price_check',return_value={'status':'queued','rows':[],'total':8}) as queue:
            response = self.client.post('/api/ecommerce/admin/ensure-prices/', {}, format='json')
        queue.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'],'queued')
        self.assertNotIn('gold_ok',response.data)
        with patch('ecommerce.price_ensure.last_price_report',return_value={'status':'completed','rows':[]}) :
            saved = self.client.get('/api/ecommerce/admin/ensure-prices/')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data['status'],'completed')

    def test_guests_cannot_ensure_prices(self):
        guest = APIClient()
        self.assertIn(guest.post('/api/ecommerce/admin/ensure-prices/').status_code, (401, 403))


class CatalogSyncApiTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='sync-staff', password='test-only', fullName='Sync Staff')
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        CustomerToken.objects.create(key='sync-test-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer sync-test-token', HTTP_X_FORWARDED_PROTO='https')

    def test_staff_can_read_and_queue_catalog_sync(self):
        with patch('ecommerce.catalog_sync_control.queue_or_run_sync', return_value={
            'status': 'queued', 'queued': True, 'ran': False, 'records': 0,
        }):
            response = self.client.post('/api/ecommerce/admin/catalog-sync/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['queued'])
        with patch('ecommerce.catalog_sync_control.last_catalog_report', return_value={
            'status': 'completed', 'records': 2, 'created': 1, 'updated': 1,
        }):
            saved = self.client.get('/api/ecommerce/admin/catalog-sync/')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data['status'], 'completed')
        self.assertEqual(saved.data['records'], 2)

    def test_guests_cannot_sync_catalog(self):
        guest = APIClient()
        self.assertIn(guest.post('/api/ecommerce/admin/catalog-sync/').status_code, (401, 403))


class UploadBuildApiTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='deploy-staff', password='test-only', fullName='Deploy Staff')
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        CustomerToken.objects.create(key='deploy-test-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer deploy-test-token', HTTP_X_FORWARDED_PROTO='https')

    def test_superuser_can_queue_upload_and_build(self):
        with patch('ecommerce.upload_build.queue_or_run_deploy', return_value={
            'status': 'running', 'percent': 5, 'activity': 'Starting Upload & Build',
        }):
            response = self.client.post('/api/ecommerce/admin/upload-build/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'running')
        with patch('ecommerce.upload_build.last_deploy_report', return_value={
            'status': 'completed', 'percent': 100, 'activity': 'Live site uploaded and built',
        }):
            saved = self.client.get('/api/ecommerce/admin/upload-build/')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data['percent'], 100)

    def test_staff_without_collect_permission_cannot_upload_and_build(self):
        self.user.is_superuser = False
        self.user.save(update_fields=['is_superuser'])
        self.assertEqual(self.client.post('/api/ecommerce/admin/upload-build/', {}, format='json').status_code, 403)


class CatalogSyncProgressTests(SimpleTestCase):
    def test_running_status_exposes_percent_for_the_progress_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BASE_DIR=tmp):
                folder = Path(tmp) / 'private_suppliers' / 'catalog_sync'
                folder.mkdir(parents=True)
                (folder / 'status.json').write_text(json.dumps({
                    'status': 'running',
                    'activity': 'Synchronizing original product photos',
                    'percent': 55,
                    'updated_at': '2026-10-28T00:00:00+00:00',
                    'run': 'progress-test',
                }), encoding='utf-8')
                from ecommerce.catalog_sync_control import last_catalog_report
                report = last_catalog_report()
                self.assertEqual(report['status'], 'running')
                self.assertEqual(report['percent'], 55)
                self.assertEqual(report['activity'], 'Synchronizing original product photos')


class CatalogSyncScriptTests(SimpleTestCase):
    def test_on_demand_status_lines_print_on_windows_console(self):
        from pathlib import Path
        script = Path(__file__).resolve().parents[2] / 'deploy' / 'sync-catalog.py'
        text = script.read_text(encoding='utf-8')
        self.assertNotIn('\u2192', text)
        text.encode('cp1252')
