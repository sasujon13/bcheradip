from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from cryptography.fernet import Fernet
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from cheradip.models import Customer, CustomerToken
from .models import (Supplier, SupplierOffer, SupplierEvidence, SupplierDecision, SupplierJob,
                     SupplierAudit, SupplierPolicy, Category, Product, ProductVariant, DeliverySettings)
from .supplier_service import (approve, assert_current, import_draft, match_key, queue_job, run_jobs, screen,
                               nightly, cleanup, policy, snapshot_row)


class SupplierTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='source-staff', password='test-only', fullName='Source Staff')
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        CustomerToken.objects.create(key='source-test-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer source-test-token', HTTP_X_FORWARDED_PROTO='https')
        self.supplier = Supplier.objects.using('ecommerce').create(name='Test supplier', website='https://supplier.example',
            enabled=True, terms_confirmed=True, terms_note='Test-only approved export licence and domestic fulfilment quote')
        self.category = Category.objects.using('ecommerce').create(name='Test', slug='source-test')
        DeliverySettings.objects.using('ecommerce').create(cost_defaults={
            'ads_cost': '0', 'packaging_cost': '0', 'returns_allowance': '0', 'other_costs': '0'})

    def row(self, external='P1', **overrides):
        return dict(external_id=external, variant_id='blue', vendor_id='vendor1', warehouse_id='warehouse1', title='Exact Product',
            url='https://supplier.example/product1', identity={'brand': 'Brand', 'model': 'M1', 'variant': 'Blue',
            'pack_count': 1, 'condition': 'new', 'warranty': '1 year', 'accessories': 'Cable', 'authenticity': 'genuine', 'tax_basis': 'included'}, source_price='100.00',
            currency='BDT', availability='in_stock', quantity=20, weight_grams=200, single_unit=True,
            observed_at=(timezone.now() - timedelta(minutes=5)).isoformat(), **overrides)

    def test_staff_source_progress_is_separate_from_legacy_offer_counts(self):
        from .models import SupplierRecollectionRun
        SupplierRecollectionRun.objects.using('ecommerce').create(supplier=self.supplier,mode='full',status='running',
            processed=72,expected_total=100,counts={'complete':70,'failed':2},activity='Reading source products')
        response=self.client.get('/api/ecommerce/admin/suppliers/')
        self.assertEqual(response.status_code,200)
        row=response.data['results'][0]
        self.assertEqual(row['fresh_source']['processed'],72)
        self.assertEqual(row['counts']['total'],0)
        self.assertNotIn('raw_data',row['fresh_source']);self.assertNotIn('credentials_ciphertext',row)

    def offer(self):
        queue_job(self.supplier.pk, 'collect', self.user.pk, [self.row()])
        run_jobs()
        return SupplierOffer.objects.using('ecommerce').get()

    def ready(self, prices=('150', '155', '160')):
        offer = self.offer()
        offer.match_confirmed = True
        offer.costs = {'supplier_shipping': '80', 'customer_shipping': '80', 'fees': '0'}
        offer.save(using='ecommerce')
        for n, price in enumerate(prices):
            self.evidence(offer, str(n), price)
        screen(offer, self.user.pk)
        offer.refresh_from_db(using='ecommerce')
        return offer

    def evidence(self, offer, seller, price, **kwargs):
        kwargs.setdefault('match_confidence', 100)
        return SupplierEvidence.objects.using('ecommerce').create(offer=offer, seller='Seller ' + seller,
            marketplace='Test market', url=f'https://market.example/listing/{seller}', price=price,
            observed_at=timezone.now() - timedelta(minutes=10), exact_match=True, match_key=offer.match_key,
            actor_id=self.user.pk, note='Exact single unit, variant, warranty and condition verified for test', **kwargs)

    def grant(self, codename):
        ct, _ = ContentType.objects.get_or_create(app_label='ecommerce', model='supplier')
        perm, _ = Permission.objects.get_or_create(content_type=ct, codename=codename, defaults={'name': codename})
        self.user.user_permissions.add(perm)

    def test_collection_is_incremental_and_does_not_import(self):
        queue_job(self.supplier.pk, 'collect', self.user.pk, [self.row()])
        self.assertEqual(run_jobs(), 1)
        self.assertEqual(SupplierJob.objects.using('ecommerce').get().status, 'completed')
        queue_job(self.supplier.pk, 'collect', self.user.pk, [self.row(), self.row('P2')])
        run_jobs()
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 2)
        self.assertEqual(Product.objects.using('ecommerce').count(), 0)
        self.assertEqual(SupplierJob.objects.using('ecommerce').latest('created_at').counts, {'existing': 1, 'new': 1})

    def test_selection_ranges_cover_filtered_products_not_just_a_page(self):
        SupplierOffer.objects.using('ecommerce').bulk_create([SupplierOffer(supplier=self.supplier,
            external_id=f'select-{n}', vendor_id='vendor', title='Chosen' if n < 1001 else 'Other',
            url='https://supplier.example/product', source_price=n + 1) for n in range(1002)])
        for size in (100, 500, 1000):
            result = self.client.get('/api/ecommerce/admin/supplier-offers/selection/',
                {'selection': size, 'search': 'Chosen', 'ordering': '-source_price'})
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(result.data['count'], size)
            self.assertEqual(result.data['total'], 1001)
            first = SupplierOffer.objects.using('ecommerce').get(pk=result.data['ids'][0])
            self.assertEqual(first.source_price, Decimal('1001'))
        result = self.client.get('/api/ecommerce/admin/supplier-offers/selection/', {'selection': 'all', 'search': 'Chosen'})
        self.assertEqual(len(result.data['ids']), 1001)
        self.assertEqual(self.client.get('/api/ecommerce/admin/supplier-offers/selection/', {'selection': '2000'}).status_code, 400)
        self.user.is_staff = False; self.user.save()
        self.assertEqual(self.client.get('/api/ecommerce/admin/supplier-offers/selection/').status_code, 403)

    def test_bulk_screening_over_1000_is_one_scoped_resumable_job(self):
        SupplierOffer.objects.using('ecommerce').bulk_create([SupplierOffer(supplier=self.supplier,
            external_id=f'bulk-{n}', vendor_id='vendor', title='Chosen', url='https://supplier.example/item',
            source_price=100) for n in range(1002)])
        ids = list(self.supplier.offers.order_by('pk').values_list('pk', flat=True))[:1001]
        result = self.client.post('/api/ecommerce/admin/supplier-jobs/selected/', {'action': 'filter', 'offer_ids': ids}, format='json')
        self.assertEqual(result.status_code, 202, result.data)
        self.assertEqual(result.data['queued'][0]['count'], 1001)
        job = SupplierJob.objects.using('ecommerce').get()
        self.assertEqual(job.total, 1001); self.assertEqual(job.payload['ids'], ids)
        run_jobs(max_items=1); job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.processed, 1)
        self.assertEqual(Product.objects.using('ecommerce').count(), 0)

    def test_bulk_update_reports_unsupported_sources_and_rejects_missing_ids(self):
        offer = self.offer()
        result = self.client.post('/api/ecommerce/admin/supplier-jobs/selected/', {'action': 'update', 'offer_ids': [offer.pk]}, format='json')
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.data['queued'], [])
        self.assertIn('No unattended', result.data['skipped'][0]['reason'])
        self.assertEqual(result.data['skipped'][0]['count'], 1)
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-jobs/selected/',
            {'action': 'update', 'offer_ids': [offer.pk + 99999]}, format='json').status_code, 400)

    def test_selected_live_update_cannot_update_unselected_identities(self):
        queue_job(self.supplier.pk, 'collect', self.user.pk, [self.row('P1'), self.row('P2')]); run_jobs()
        self.supplier.connector = 'business_koro'; self.supplier.credentials_ciphertext = 'test-only-placeholder'
        self.supplier.save(using='ecommerce')
        one, two = list(self.supplier.offers.order_by('pk'))
        result = self.client.post('/api/ecommerce/admin/supplier-jobs/selected/', {'action': 'update', 'offer_ids': [one.pk]}, format='json')
        self.assertEqual(result.status_code, 202, result.data)
        rows = [self.row('P1'), self.row('P2')]
        for row in rows:
            row.update(source_price='125', observed_at=timezone.now().isoformat())
        with patch('ecommerce.supplier_connectors.collect', return_value=(rows, {})):
            run_jobs()
        one.refresh_from_db(using='ecommerce'); two.refresh_from_db(using='ecommerce')
        self.assertEqual(one.source_price, Decimal('125'))
        self.assertEqual(two.source_price, Decimal('100'))

    def test_partial_api_feed_reports_unreturned_tracked_products_without_fabricating_stock(self):
        queue_job(self.supplier.pk, 'collect', self.user.pk, [self.row('P1'), self.row('P2')]); run_jobs()
        self.supplier.connector='business_koro'; self.supplier.credentials_ciphertext='synthetic-placeholder'; self.supplier.save(using='ecommerce')
        job=queue_job(self.supplier.pk,'update',self.user.pk)
        row=self.row('P1'); row.update(source_price='125',observed_at=timezone.now().isoformat())
        with patch('ecommerce.supplier_connectors.collect',return_value=([row],{})): run_jobs()
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status,'completed_with_errors')
        self.assertEqual(job.counts['unreturned_tracked'],1)
        self.assertIn('not returned',job.errors[0]['message'])
        missing=self.supplier.offers.get(external_id='P2')
        self.assertEqual(missing.source_price,Decimal('100')); self.assertEqual(missing.quantity,20)

    def test_similarity_and_lowest_three_evidence_are_preserved_for_manual_review(self):
        offer = self.ready()
        body = {'seller': 'New seller', 'marketplace': 'Market', 'url': 'https://new-seller.example/exact',
            'price': '125', 'delivery': '80', 'observed_at': timezone.now().isoformat(), 'exact_match': True,
            'match_confidence': '97.25', 'available': True, 'note': 'Exact model, variant and warranty checked.'}
        url = f'/api/ecommerce/admin/supplier-offers/{offer.pk}/evidence/'
        result = self.client.post(url, body, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['match_confidence'], '97.25')
        decision = screen(offer, self.user.pk)
        self.assertEqual(decision.result['competitor_prices'], ['125.00', '150.00', '155.00'])
        self.assertEqual(decision.result['benchmark'], '143.33')
        saved = decision.result['competitor_observations'][0]
        self.assertEqual(saved['url'], body['url']); self.assertEqual(saved['similarity_percent'], '97.25')
        body['match_confidence'] = '100.01'
        self.assertEqual(self.client.post(url, body, format='json').status_code, 400)
        body.update(match_confidence='100', exact_match=False, seller='Not equivalent', price='1', url='https://not-exact.example/item')
        self.assertEqual(self.client.post(url, body, format='json').status_code, 201)
        self.assertNotIn('1.00', screen(offer, self.user.pk).result['competitor_prices'])

    def test_incomplete_identity_can_retain_candidates_but_never_exact_evidence(self):
        offer = self.offer()
        offer.identity = {'authenticity': 'unverified', 'variant': 'Blue'}
        offer.match_key = ''
        offer.match_confirmed = False
        offer.save(using='ecommerce')
        body = {'seller': 'Candidate seller', 'marketplace': 'Market',
            'url': 'https://candidate.example/product', 'price': '120',
            'observed_at': timezone.now().isoformat(), 'exact_match': False,
            'match_confidence': '70', 'available': True,
            'note': 'Title and colour agree; material, warranty and authenticity remain unverified.'}
        endpoint = f'/api/ecommerce/admin/supplier-offers/{offer.pk}/evidence/'
        result = self.client.post(endpoint, body, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['match_confidence'], '70.00')
        self.assertEqual(result.data['match_key'], '')
        body['exact_match'] = True
        self.assertEqual(self.client.post(endpoint, body, format='json').status_code, 400)
        decision = screen(offer, self.user.pk)
        self.assertEqual(decision.result['competitor_prices'], [])
        self.assertIsNone(decision.result['benchmark'])
        # Confirming the source later must not promote the old candidate.
        offer.identity = self.row()['identity']
        offer.match_key = match_key(offer.identity)
        offer.match_confirmed = True
        offer.save(using='ecommerce')
        self.assertEqual(screen(offer, self.user.pk).result['competitor_prices'], [])

    def test_specific_source_url_can_be_corrected_without_unsafe_fetch_or_old_approval(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Checked')
        result = self.client.post(f'/api/ecommerce/admin/supplier-offers/{offer.pk}/review/',
            {'url': 'https://supplier.example/specific-product/variant-blue'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        offer.refresh_from_db(using='ecommerce')
        self.assertTrue(offer.url.endswith('variant-blue'))
        with self.assertRaises(ValueError): assert_current(offer)
        result = self.client.post(f'/api/ecommerce/admin/supplier-offers/{offer.pk}/review/',
            {'url': 'http://127.0.0.1/private'}, format='json')
        self.assertEqual(result.status_code, 400)

    @override_settings(COMMERCE_SUPPLIER_KEY=Fernet.generate_key().decode())
    def test_partial_credentials_change_preserves_issued_secret_without_returning_it(self):
        from .supplier_crypto import decrypt
        url = f'/api/ecommerce/admin/suppliers/{self.supplier.pk}/credentials/'
        result = self.client.post(url, {'credentials': {'api_key': 'old-test-key', 'api_secret': 'test-secret', 'domain': 'shop.example'}}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        result = self.client.post(url, {'credentials': {'api_key': 'new-test-key'}, 'merge': True}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.supplier.refresh_from_db(using='ecommerce')
        self.assertEqual(decrypt(self.supplier), {'api_key': 'new-test-key', 'api_secret': 'test-secret', 'domain': 'shop.example'})
        self.assertNotIn('test-secret', str(result.data)); self.assertNotIn('new-test-key', str(result.data))

    def test_supplier_wide_filter_exceeds_1000_with_bounded_resumable_cursor(self):
        SupplierOffer.objects.using('ecommerce').bulk_create([SupplierOffer(supplier=self.supplier,
            external_id=f'large-{n}',vendor_id='vendor',title='Unverified',url='https://supplier.example/product',source_price=100)
            for n in range(1001)])
        job=queue_job(self.supplier.pk,'filter',self.user.pk)
        self.assertEqual(job.total,1001)
        self.assertNotIn('ids',job.payload)
        boundary=job.payload['through_id']
        run_jobs(max_items=2)
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.processed,2)
        self.assertGreater(job.payload['after_id'],0)
        self.assertEqual(job.payload['through_id'],boundary)
        self.assertEqual(job.status,'running')
        job.status='cancel_requested';job.save(using='ecommerce')
        run_jobs(max_items=1)
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status,'cancelled')
        self.assertEqual(job.processed,2)

    def test_vendor_offers_preserved_and_pack_sizes_not_merged(self):
        a = self.row(); b = self.row(); b['vendor_id'] = 'vendor2'
        c = self.row('P3'); c['identity']['pack_count'] = 2
        queue_job(self.supplier.pk, 'collect', rows=[a, b, c]); run_jobs()
        rows = list(SupplierOffer.objects.using('ecommerce').order_by('id'))
        self.assertEqual(rows[0].match_key, rows[1].match_key)
        self.assertNotEqual(rows[0].match_key, rows[2].match_key)

    def test_conflicting_identity_quarantined_without_overwrite(self):
        offer = self.offer()
        row = self.row(); row['identity']['model'] = 'Different'
        queue_job(self.supplier.pk, 'collect', rows=[row]); run_jobs()
        offer.refresh_from_db(using='ecommerce')
        self.assertEqual(offer.identity['model'], 'M1')
        self.assertEqual(offer.state, 'needs_review')
        self.assertFalse(offer.match_confirmed)

    def test_source_update_only_does_not_import_discover_or_change_content(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Checked')
        product, _ = import_draft(offer, self.category.pk, self.user.pk)
        row = self.row(); row.update(source_price='120.00', title='Do not overwrite', quantity=2, observed_at=timezone.now().isoformat())
        queue_job(self.supplier.pk, 'update', rows=[row, self.row('missing')]); run_jobs()
        offer.refresh_from_db(using='ecommerce'); product.refresh_from_db(using='ecommerce')
        self.assertEqual(offer.source_price, Decimal('120.00'))
        self.assertEqual(offer.title, 'Exact Product')
        self.assertEqual(product.variants.first().price, Decimal('120.00'))
        self.assertEqual(product.variants.first().stock, 0)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 1)
        self.assertEqual(offer.state, 'needs_review')

    def test_update_rejects_older_observation(self):
        offer = self.offer()
        row = self.row(); row.update(source_price='1', observed_at=(timezone.now() - timedelta(days=1)).isoformat())
        queue_job(self.supplier.pk, 'update', rows=[row]); run_jobs()
        offer.refresh_from_db(using='ecommerce')
        self.assertEqual(offer.source_price, Decimal('100'))

    def test_ready_benchmark_is_average_of_three_lowest_independent_sellers(self):
        offer = self.ready(prices=('150', '180', '270'))
        self.evidence(offer, 'fourth', '900')
        result = screen(offer).result
        self.assertEqual(result['benchmark'], '200.00')  # Not median 180.
        self.assertEqual(result['competitor_prices'], ['150.00', '180.00', '270.00'])
        self.assertEqual(SupplierOffer.objects.using('ecommerce').get().state, 'ready')

    def test_duplicate_seller_does_not_complete_benchmark(self):
        offer = self.ready()
        offer.evidence.all().delete()
        for price in ('130', '140', '150'):
            self.evidence(offer, 'same', price)
        self.assertEqual(screen(offer).state, 'needs_data')

    def test_new_unavailable_evidence_supersedes_old_available_advert(self):
        offer = self.ready()
        self.evidence(offer, '0', '1', available=False)
        self.assertEqual(screen(offer).state, 'needs_data')

    def test_blacklist_zero_margin_and_reduced_margin(self):
        offer = self.ready(prices=('99', '99', '99'))
        self.assertEqual(offer.state, 'blacklist')
        for price, expected in [('100', 'zero_margin'), ('110', 'reduced_margin'), ('150', 'ready')]:
            offer.evidence.all().update(price=price)
            self.assertEqual(screen(offer).state, expected)
        self.assertGreater(offer.decisions.count(), 3)

    def test_permanent_exclusion_survives_price_recovery(self):
        offer = self.ready()
        offer.excluded_reason = 'Counterfeit risk'; offer.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'excluded')
        row = self.row(); row['observed_at'] = timezone.now().isoformat(); row['source_price'] = '1'
        queue_job(self.supplier.pk, 'update', rows=[row]); run_jobs()
        offer.refresh_from_db(using='ecommerce')
        self.assertEqual(offer.state, 'excluded')

    def test_missing_evidence_and_unconfirmed_match_never_auto_pass(self):
        offer = self.offer()
        self.assertEqual(screen(offer).state, 'needs_review')
        offer.match_confirmed = True; offer.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'needs_data')

    def test_fulfilled_loss_weight_and_shipping_require_review(self):
        offer = self.ready()
        offer.costs['supplier_shipping'] = '500'; offer.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'needs_review')
        offer.costs = {}; offer.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'needs_review')

    def test_non_delivery_floor_excludes_shipping_and_includes_fees(self):
        offer = self.ready()
        offer.costs.update(ads_cost='10', fees='5', supplier_shipping='120', customer_shipping='120')
        offer.save(using='ecommerce')
        d = screen(offer)
        self.assertEqual(d.result['cost_floor'], '115.00')
        self.assertEqual(d.result['suggested_price'], '136.85')

    def test_import_requires_current_screening_and_explicit_approval(self):
        offer = self.ready()
        with self.assertRaises(ValueError): import_draft(offer, self.category.pk, self.user.pk)
        approve(offer, self.user.pk, 'Approved test')
        product, created = import_draft(offer, self.category.pk, self.user.pk)
        self.assertTrue(created); self.assertEqual(product.status, 'draft')
        self.assertEqual(product.variants.first().stock, 0)
        product.name = 'Local name'; product.save(using='ecommerce')
        again, created = import_draft(offer, self.category.pk, self.user.pk)
        self.assertFalse(created); self.assertEqual(again.name, 'Local name')

    def test_source_change_or_settings_change_invalidates_approval(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Approve')
        offer.source_price = '101'; offer.save(using='ecommerce')
        with self.assertRaises(ValueError): import_draft(offer, self.category.pk, self.user.pk)
        screen(offer); approve(offer, self.user.pk, 'Approve updated')
        config = policy(); config.revision += 1; config.save(using='ecommerce')
        with self.assertRaises(ValueError): import_draft(offer, self.category.pk, self.user.pk)

    def test_fresh_screen_does_not_rejuvenate_expired_evidence(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Approve')
        future = timezone.now() + timedelta(days=15)
        with patch('ecommerce.supplier_service.timezone.now', return_value=future):
            with self.assertRaises(ValueError): import_draft(offer, self.category.pk, self.user.pk)
            self.assertEqual(screen(offer).state, 'needs_data')

    def test_cancellation_checkpoint_and_duplicate_protection(self):
        job = queue_job(self.supplier.pk, 'collect', rows=[self.row('A'), self.row('B')])
        with self.assertRaises(ValueError): queue_job(self.supplier.pk, 'collect', rows=[self.row()])
        run_jobs(max_items=1)
        SupplierJob.objects.using('ecommerce').filter(pk=job.pk).update(status='cancel_requested')
        run_jobs()
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status, 'cancelled'); self.assertEqual(job.processed, 1)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 1)

    def test_worker_resumes_and_does_not_overlap(self):
        job = queue_job(self.supplier.pk, 'collect', rows=[self.row('A'), self.row('B')])
        run_jobs(max_items=1)
        config = policy(); config.worker_until = timezone.now() + timedelta(minutes=3); config.save(using='ecommerce')
        self.assertEqual(run_jobs(), 0)
        config.worker_until = timezone.now() - timedelta(seconds=1); config.save(using='ecommerce')
        run_jobs(); job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.processed, 2); self.assertEqual(job.status, 'completed')

    def test_disabled_supplier_job_stops_without_processing(self):
        job = queue_job(self.supplier.pk, 'collect', rows=[self.row()])
        self.supplier.enabled = False; self.supplier.save(using='ecommerce')
        run_jobs(); job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status, 'failed'); self.assertEqual(job.processed, 0)

    def test_nightly_is_dhaka_once_daily_and_never_fakes_stock_check(self):
        offer = self.offer(); old_time = offer.observed_at
        now = timezone.datetime(2026, 10, 20, 17, 59, tzinfo=timezone.get_default_timezone())
        # Supply UTC explicitly; settings default timezone may change independently.
        from datetime import timezone as dt_timezone
        now = now.replace(tzinfo=dt_timezone.utc)
        with patch('ecommerce.supplier_service.timezone.now', return_value=now):
            self.assertEqual(nightly(), 1); self.assertEqual(nightly(), 0)
        offer.refresh_from_db(using='ecommerce')
        self.assertEqual(offer.observed_at, old_time)
        self.assertEqual(policy().last_nightly_date.isoformat(), '2026-10-20')

    def test_cleanup_keeps_decisions_audits_and_active_jobs(self):
        offer = self.ready()
        old = timezone.now() - timedelta(days=100)
        SupplierJob.objects.using('ecommerce').update(finished_at=old)
        queue_job(self.supplier.pk, 'filter', offer_ids=[offer.pk])
        self.assertGreater(cleanup(), 0)
        self.assertTrue(SupplierJob.objects.using('ecommerce').filter(status='queued').exists())
        self.assertTrue(SupplierDecision.objects.using('ecommerce').exists())
        self.assertTrue(SupplierAudit.objects.using('ecommerce').exists())

    def test_permissions_regular_customer_and_staff_with_view_only_cannot_write(self):
        self.user.is_superuser = self.user.is_staff = False; self.user.save()
        self.assertEqual(self.client.get('/api/ecommerce/admin/suppliers/').status_code, 403)
        self.user.is_staff = True; self.user.save(); self.grant('view_supplier')
        self.assertEqual(self.client.get('/api/ecommerce/admin/suppliers/').status_code, 200)
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-jobs/', {'supplier': self.supplier.pk, 'action': 'collect', 'rows': [self.row()]}, format='json').status_code, 403)
        self.grant('collect_supplier')
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-jobs/', {'supplier': self.supplier.pk, 'action': 'collect', 'rows': [self.row()]}, format='json').status_code, 202)

    @override_settings(COMMERCE_SUPPLIER_KEY=Fernet.generate_key().decode())
    def test_credentials_encrypted_never_returned_or_logged(self):
        url = f'/api/ecommerce/admin/suppliers/{self.supplier.pk}/credentials/'
        result = self.client.post(url, {'credentials': {'api_key': 'secret-value-test'}}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.supplier.refresh_from_db(using='ecommerce')
        self.assertNotIn('secret-value-test', self.supplier.credentials_ciphertext)
        payload = self.client.get('/api/ecommerce/admin/suppliers/').content.decode()
        self.assertNotIn('secret-value-test', payload); self.assertNotIn('credentials_ciphertext', payload)
        self.assertNotIn('secret-value-test', str(list(SupplierAudit.objects.using('ecommerce').values())))

    @override_settings(COMMERCE_SUPPLIER_KEY='', COMMERCE_SUPPLIER_KEY_FILE='')
    def test_missing_encryption_key_fails_closed(self):
        result = self.client.post(f'/api/ecommerce/admin/suppliers/{self.supplier.pk}/credentials/', {'credentials': {'api_key': 'test'}}, format='json')
        self.assertEqual(result.status_code, 400)

    def test_invalid_payload_and_private_network_reference_rejected(self):
        row = self.row(); row['url'] = 'http://127.0.0.1/private'; row['source_price'] = '-1'
        result = self.client.post('/api/ecommerce/admin/supplier-jobs/', {'supplier': self.supplier.pk, 'action': 'collect', 'rows': [row]}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertEqual(SupplierJob.objects.using('ecommerce').count(), 0)

    def test_api_review_evidence_preview_import_end_to_end_without_purchase(self):
        offer = self.offer(); base = f'/api/ecommerce/admin/supplier-offers/{offer.pk}'
        response = self.client.post(base + '/review/', {'match_confirmed': True, 'costs': {'supplier_shipping': '80', 'customer_shipping': '80', 'fees': '0'}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        for n in range(3):
            response = self.client.post(base + '/evidence/', {'seller': f'Seller {n}', 'marketplace': 'Test marketplace',
                'url': f'https://market.example/p/{n}', 'price': '150', 'observed_at': timezone.now().isoformat(),
                'exact_match': True, 'match_confidence':100, 'available': True, 'note': 'All variant, condition, warranty and pack details verified'}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
        queue_job(self.supplier.pk, 'filter', offer_ids=[offer.pk]); run_jobs()
        response = self.client.post(base + '/approval/', {'note': 'Test-only approval'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        data = {'ids': [offer.pk], 'category': self.category.pk, 'preview': True}
        response = self.client.post('/api/ecommerce/admin/supplier-import/', data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(Product.objects.using('ecommerce').exists())
        data['preview_token'] = response.json()['preview_token']
        data['preview'] = False
        response = self.client.post('/api/ecommerce/admin/supplier-import/', data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Product.objects.using('ecommerce').get().status, 'draft')
        self.assertFalse(self.client.get('/api/ecommerce/admin/supplier-workspace/').json()['auto_place_orders'])

    def test_shortlist_setup_is_disabled_idempotent_and_has_no_products(self):
        call_command('setup_supplier_shortlist', verbosity=0)
        call_command('setup_supplier_shortlist', verbosity=0)
        self.assertEqual(Supplier.objects.using('ecommerce').count(), 10)
        self.assertEqual(Supplier.objects.using('ecommerce').filter(enabled=False).count(), 9)
        self.assertFalse(Supplier.objects.using('ecommerce').filter(name='eSell.bd').exists())
        self.assertFalse(Product.objects.using('ecommerce').exists())

    def test_cheaper_equivalent_is_reviewed_before_expensive_source(self):
        offer = self.ready()
        row = self.row('CHEAPER'); row['vendor_id'] = 'vendor2'; row['source_price'] = '90'
        queue_job(self.supplier.pk, 'collect', rows=[row]); run_jobs()
        alternative = SupplierOffer.objects.using('ecommerce').exclude(pk=offer.pk).get()
        alternative.match_confirmed = True; alternative.save(using='ecommerce')
        decision = screen(offer)
        self.assertEqual(decision.state, 'needs_review')
        self.assertEqual(decision.result['lowest_source_offer'], alternative.pk)
        alternative.state = 'blacklist'; alternative.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'ready')  # A rejected offer must not reject the viable alternative.

    def test_same_exact_product_cannot_be_imported_from_two_suppliers(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Approve')
        import_draft(offer, self.category.pk, self.user.pk)
        row = self.row('OTHER'); queue_job(self.supplier.pk, 'collect', rows=[row]); run_jobs()
        other = SupplierOffer.objects.using('ecommerce').exclude(pk=offer.pk).get()
        other.match_confirmed = True; other.costs = offer.costs; other.save(using='ecommerce')
        for i in range(3): self.evidence(other, str(i), '150')
        screen(other); approve(other, self.user.pk, 'Approve comparison')
        with self.assertRaisesRegex(ValueError, 'already imported'):
            import_draft(other, self.category.pk, self.user.pk)
        self.assertEqual(Product.objects.using('ecommerce').count(), 1)

    def test_nightly_style_update_keeps_price_blacklist_recheckable(self):
        offer = self.ready(prices=('99', '99', '99'))
        row = self.row(); row['observed_at'] = timezone.now().isoformat(); row['source_price'] = '50'
        queue_job(self.supplier.pk, 'update', rows=[row]); run_jobs()
        offer.refresh_from_db(using='ecommerce'); self.assertEqual(offer.state, 'blacklist')
        queue_job(self.supplier.pk, 'recheck'); run_jobs()
        offer.refresh_from_db(using='ecommerce'); self.assertEqual(offer.state, 'ready')

    def test_staging_publication_and_checkout_are_blocked_even_after_raw_status_change(self):
        from django.core.exceptions import ValidationError
        from .models import Cart, CartItem, Order
        offer = self.ready(); approve(offer, self.user.pk, 'Approved draft')
        product, _ = import_draft(offer, self.category.pk, self.user.pk)
        product.status = 'active'
        with self.assertRaises(ValueError): product.save(using='ecommerce')
        with self.assertRaises(ValidationError): product.clean()
        response = self.client.patch(f'/api/ecommerce/admin/products/{product.pk}/', {'status': 'active'}, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        Product.objects.using('ecommerce').filter(pk=product.pk).update(status='active')
        variant = product.variants.first()
        ProductVariant.objects.using('ecommerce').filter(pk=variant.pk).update(stock=10, allow_backorder=True)
        self.assertEqual(self.client.get('/api/ecommerce/products/').json()['count'], 0)
        self.assertEqual(self.client.get(f'/api/ecommerce/products/{product.slug}/').status_code, 404)
        self.assertEqual(self.client.post('/api/ecommerce/cart/', {'variant_id': variant.pk}, format='json').status_code, 409)
        cart = Cart.objects.using('ecommerce').create(customer_id=self.user.pk)
        CartItem.objects.using('ecommerce').create(cart=cart, variant=variant, quantity=1)
        payload = {'cart_token': cart.token, 'customer_name': 'Buyer', 'phone': '01710000000',
            'email': 'buyer@example.com', 'shipping_address': {'country_code': 'BD', 'district': 'Dhaka', 'thana': 'Savar', 'address': 'Road 1'}, 'payment_method': 'cod'}
        self.assertEqual(self.client.post('/api/ecommerce/checkout/quote/', payload, format='json').status_code, 409)
        self.assertEqual(self.client.post('/api/ecommerce/checkout/', payload, format='json').status_code, 409)
        self.assertFalse(Order.objects.using('ecommerce').exists())
        variant.refresh_from_db(using='ecommerce'); self.assertEqual(variant.stock, 10)

    def test_update_reused_identity_quarantines_instead_of_repricing(self):
        offer = self.ready()
        row = self.row(); row['identity']['model'] = 'Another product'; row['source_price'] = '1'
        row['observed_at'] = timezone.now().isoformat()
        queue_job(self.supplier.pk, 'update', self.user.pk, rows=[row]); run_jobs()
        offer.refresh_from_db(using='ecommerce')
        self.assertEqual(offer.source_price, Decimal('100'))
        self.assertFalse(offer.match_confirmed)
        self.assertEqual(offer.state, 'needs_review')
        self.assertEqual(SupplierAudit.objects.using('ecommerce').get(action='identity_conflict').detail['incoming_identity']['model'], 'Another product')

    def test_authenticity_and_specifications_do_not_merge(self):
        genuine = self.row()['identity']; replica = dict(genuine, authenticity='replica')
        self.assertNotEqual(match_key(genuine), match_key(replica))
        self.assertEqual(match_key(dict(genuine, authenticity='unverified')), '')
        self.assertNotEqual(match_key(dict(genuine, specifications={'capacity': '64GB'})), match_key(dict(genuine, specifications={'capacity': '128GB'})))

    def test_dimensions_and_tax_basis_survive_collection_and_review(self):
        row = self.row(); row['identity'].update(tax_basis='included', dimensions={'length_cm': '10.00', 'width_cm': '3.00', 'height_cm': '2.00'})
        queue_job(self.supplier.pk, 'collect', rows=[row]); run_jobs()
        offer = SupplierOffer.objects.using('ecommerce').get()
        self.assertEqual(offer.identity['dimensions']['width_cm'], '3.00')
        response = self.client.post(f'/api/ecommerce/admin/supplier-offers/{offer.pk}/review/',
            {'identity': offer.identity, 'match_confirmed': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.json()['identity']['tax_basis'], 'included')

    def test_new_matching_rule_invalidates_an_old_decision(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Approved')
        offer.current_decision.result['rule_version'] = 1
        offer.current_decision.save(using='ecommerce')
        with self.assertRaises(ValueError): import_draft(offer, self.category.pk, self.user.pk)

    def test_recovered_cheaper_alternative_invalidates_prior_approval(self):
        offer = self.ready()
        row = self.row('Cheap'); row['source_price'] = '90'
        queue_job(self.supplier.pk, 'collect', rows=[row]); run_jobs()
        other = SupplierOffer.objects.using('ecommerce').exclude(pk=offer.pk).get()
        other.match_confirmed = True; other.state = 'blacklist'; other.save(using='ecommerce')
        screen(offer); approve(offer, self.user.pk, 'Cheaper source rejected; viable alternative checked')
        other.state = 'ready'; other.save(using='ecommerce')
        with self.assertRaises(ValueError): import_draft(offer, self.category.pk, self.user.pk)

    def test_all_observed_price_flag_includes_more_than_selected_three(self):
        offer = self.ready(prices=('50', '60', '70'))
        self.evidence(offer, 'expensive', '200')
        result = screen(offer).result
        self.assertEqual(result['competitor_prices'], ['50.00', '60.00', '70.00'])
        self.assertFalse(result['source_above_all_observed'])
        self.assertEqual(result['valid_independent_seller_count'], 4)

    def test_all_cost_target_is_distinct_from_product_only_comparison(self):
        offer = self.ready(); offer.costs = {'supplier_shipping': '90', 'customer_shipping': '80', 'fees': '0'}; offer.save(using='ecommerce')
        result = screen(offer).result
        self.assertEqual(result['suggested_price'], '120.00')
        self.assertEqual(result['all_cost_suggested_price'], '130.90')
        self.assertEqual(result['delivered_profit_at_suggested'], '10.00')
        self.assertEqual(result['cost_origins']['ads_cost'], 'central_estimate')

    @override_settings(COMMERCE_SUPPLIER_KEY='')
    def test_credentials_can_be_cleared_when_encryption_key_is_unavailable(self):
        self.supplier.credentials_ciphertext = 'previous-encrypted-value'; self.supplier.save(using='ecommerce')
        response = self.client.post(f'/api/ecommerce/admin/suppliers/{self.supplier.pk}/credentials/', {'credentials': {}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.supplier.refresh_from_db(using='ecommerce'); self.assertEqual(self.supplier.credentials_ciphertext, '')

    def test_unconfirmed_tax_and_missing_fee_quotes_hold_import(self):
        offer = self.ready()
        offer.identity['tax_basis'] = 'unconfirmed'; offer.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'needs_review')
        offer.identity['tax_basis'] = 'included'; offer.costs.pop('fees'); offer.save(using='ecommerce')
        decision = screen(offer)
        self.assertEqual(decision.state, 'needs_review')
        self.assertEqual(decision.result['cost_origins']['fees'], 'not_provided')
        with self.assertRaises(ValueError): approve(offer, self.user.pk, 'Cannot approve unknown fees')

    def test_additional_taxes_require_quote_and_cannot_be_double_counted(self):
        offer = self.ready(); offer.identity['tax_basis'] = 'excluded'; offer.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'needs_review')
        offer.costs['taxes'] = '5'; offer.save(using='ecommerce')
        decision = screen(offer)
        self.assertEqual(decision.state, 'ready'); self.assertEqual(decision.result['cost_floor'], '105.00')
        offer.identity['tax_basis'] = 'included'; offer.save(using='ecommerce')
        self.assertEqual(screen(offer).state, 'needs_review')

    def test_foreign_source_price_is_not_added_to_bdt_cost_defaults(self):
        offer = self.ready(); offer.currency = 'USD'; offer.save(using='ecommerce')
        decision = screen(offer)
        self.assertEqual(decision.state, 'needs_data')
        self.assertEqual(decision.result['source_currency'], 'USD')
        for key in ('cost_floor', 'suggested_price', 'all_cost_suggested_price', 'source_above_all_observed'):
            self.assertIsNone(decision.result[key])

    def test_tax_basis_change_invalidates_approval_without_changing_exact_product_key(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Confirmed taxes included')
        offer.identity['tax_basis'] = 'excluded'; offer.save(using='ecommerce')
        with self.assertRaises(ValueError): import_draft(offer, self.category.pk, self.user.pk)

    def test_price_filters_accept_zero_and_reject_reversed_range(self):
        self.offer()
        url = '/api/ecommerce/admin/supplier-offers/'
        response = self.client.get(url, {'max_price': '0'})
        self.assertEqual(response.status_code, 200); self.assertEqual(response.data['count'], 0)
        self.assertEqual(self.client.get(url, {'min_price': '10', 'max_price': '0'}).status_code, 400)

    def test_evidence_cannot_be_bound_to_changed_identity(self):
        offer = self.ready()
        response = self.client.post(f'/api/ecommerce/admin/supplier-offers/{offer.pk}/evidence/', {'expected_match_key': 'old-key'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(offer.evidence.count(), 3)

    def test_confirm_requires_exact_signed_preview_and_unchanged_decision(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Approved draft')
        data = {'ids': [offer.pk], 'category': self.category.pk, 'preview': False}
        url = '/api/ecommerce/admin/supplier-import/'
        self.assertEqual(self.client.post(url, data, format='json').status_code, 400)
        preview = self.client.post(url, dict(data, preview=True), format='json').json()
        data['preview_token'] = preview['preview_token']
        screen(offer); approve(offer, self.user.pk, 'Re-approved updated decision')
        self.assertEqual(self.client.post(url, data, format='json').status_code, 400)
        self.assertFalse(Product.objects.using('ecommerce').exists())

    def test_import_preview_validates_category(self):
        offer = self.ready(); approve(offer, self.user.pk, 'Approved draft')
        response = self.client.post('/api/ecommerce/admin/supplier-import/', {'ids': [offer.pk], 'category': 999999, 'preview': True}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_revoked_staff_permission_stops_queued_work(self):
        job = queue_job(self.supplier.pk, 'collect', self.user.pk, rows=[self.row()])
        self.user.is_staff = False; self.user.save()
        run_jobs(); job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status, 'failed'); self.assertEqual(job.processed, 0)
        self.assertFalse(SupplierOffer.objects.using('ecommerce').exists())

    def test_corrupt_job_checkpoint_fails_without_crashing_worker(self):
        job = queue_job(self.supplier.pk, 'collect', self.user.pk, rows=[self.row()])
        SupplierJob.objects.using('ecommerce').filter(pk=job.pk).update(payload={'rows': []})
        run_jobs(); job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status, 'failed'); self.assertEqual(job.processed, 0)

    def test_replaced_worker_token_fences_old_process_out(self):
        job = queue_job(self.supplier.pk, 'collect', rows=[self.row('one'), self.row('two')])
        def replace_token(*args):
            outcome = snapshot_row(*args)
            SupplierPolicy.objects.using('ecommerce').filter(pk=1).update(worker_token='replacement', worker_until=timezone.now() + timedelta(minutes=5))
            return outcome
        with patch('ecommerce.supplier_service.snapshot_row', side_effect=replace_token):
            self.assertEqual(run_jobs(), 1)
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.processed, 1); self.assertEqual(policy().worker_token, 'replacement')

    def test_policy_admin_does_not_clobber_a_worker_lease(self):
        from types import SimpleNamespace
        from django.contrib.admin import site
        from .supplier_admin import SupplierPolicyAdmin, SupplierPolicyForm
        config = policy()
        stale = SupplierPolicy.objects.using('ecommerce').get(pk=1)
        config.worker_token = 'live-worker'; config.worker_until = timezone.now() + timedelta(minutes=5); config.save(using='ecommerce')
        stale.evidence_days = 10
        SupplierPolicyAdmin(SupplierPolicy, site).save_model(SimpleNamespace(user=self.user), stale, SimpleNamespace(changed_data=['evidence_days']), True)
        current = policy(); self.assertEqual(current.worker_token, 'live-worker'); self.assertEqual(current.evidence_days, 10)
        self.assertFalse(SupplierPolicyForm(data={'evidence_days': 0, 'retention_days': 90}).is_valid())

    def live_supplier(self):
        self.supplier.connector = 'business_koro'
        self.supplier.credentials_ciphertext = 'test-placeholder-not-a-real-key'
        self.supplier.save(using='ecommerce')

    def test_live_collection_commits_only_identities_and_reports_skipped_rows(self):
        self.live_supplier()
        job = queue_job(self.supplier.pk, 'collect', self.user.pk)
        self.assertEqual(job.total, 0)
        with patch('ecommerce.supplier_connectors.collect', return_value=([self.row()], {'invalid_skipped': 1})):
            run_jobs()
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status, 'completed_with_errors')
        self.assertEqual(job.processed, 1)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 1)
        self.assertFalse(Product.objects.using('ecommerce').exists())

    def test_live_update_cannot_discover_new_products_or_replace_shop_data(self):
        self.offer()
        self.live_supplier()
        job = queue_job(self.supplier.pk, 'update', self.user.pk)
        row = self.row(); row['source_price'] = '123.00'; row['observed_at'] = timezone.now().isoformat()
        with patch('ecommerce.supplier_connectors.collect', return_value=([row, self.row('not-tracked')], {})):
            run_jobs()
        self.assertEqual(SupplierOffer.objects.using('ecommerce').count(), 1)
        self.assertEqual(SupplierOffer.objects.using('ecommerce').get().source_price, Decimal('123'))
        self.assertFalse(Product.objects.using('ecommerce').exists())

    def test_live_cancellation_during_network_read_does_not_commit_rows(self):
        self.live_supplier()
        job = queue_job(self.supplier.pk, 'collect', self.user.pk)
        def cancelled(*args):
            SupplierJob.objects.using('ecommerce').filter(pk=job.pk).update(status='cancel_requested')
            return [self.row()], {}
        with patch('ecommerce.supplier_connectors.collect', side_effect=cancelled):
            run_jobs()
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status, 'cancelled')
        self.assertFalse(SupplierOffer.objects.using('ecommerce').exists())

    def test_live_connection_response_contains_counts_not_keys_or_products(self):
        self.live_supplier()
        with patch('ecommerce.supplier_connectors.collect', return_value=([self.row()], {'source_products': 1})):
            result = self.client.post(f'/api/ecommerce/admin/suppliers/{self.supplier.pk}/connection/', {}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['identity_count'], 1)
        self.assertNotIn('rows', result.data)
        self.assertNotIn('credentials', result.data)
        self.assertNotIn('Exact Product', str(result.data))

    def test_changed_source_title_without_model_metadata_is_quarantined(self):
        row = self.row(); row['identity'] = {'authenticity': 'unverified'}
        queue_job(self.supplier.pk, 'collect', self.user.pk, rows=[row]); run_jobs()
        row['title'] = 'Possibly another product'; row['source_price'] = '2.00'
        row['observed_at'] = timezone.now().isoformat()
        queue_job(self.supplier.pk, 'update', self.user.pk, rows=[row])
        run_jobs()
        offer = SupplierOffer.objects.using('ecommerce').get()
        self.assertEqual(offer.title, 'Exact Product')
        self.assertEqual(offer.source_price, Decimal('100'))
        self.assertEqual(offer.state, 'needs_review')

    def test_missing_price_is_unconfirmed_not_free_or_profitable(self):
        row = self.row(); row['source_price'] = None
        queue_job(self.supplier.pk, 'collect', self.user.pk, rows=[row]); run_jobs()
        offer = SupplierOffer.objects.using('ecommerce').get()
        self.assertIsNone(offer.source_price)
        decision = screen(offer, self.user.pk)
        self.assertEqual(decision.state, 'needs_data')
        self.assertIsNone(decision.result['suggested_price'])
        self.assertIn('not free', ' '.join(decision.result['reasons']))

    def test_regular_worker_never_consumes_browser_owned_jobs(self):
        job = SupplierJob.objects.using('ecommerce').create(supplier=self.supplier,runner='browser',action='collect',status='running')
        self.assertEqual(run_jobs(), 0)
        job.refresh_from_db(using='ecommerce')
        self.assertEqual(job.status, 'running')

    def test_browser_source_matches_website_not_database_primary_key(self):
        from .supplier_browser import start_job, CollectionStopped
        self.supplier.website = 'https://shopbasebd.com'; self.supplier.save(using='ecommerce')
        job = start_job('shopbase', self.user.pk)
        self.assertEqual(job.supplier_id, self.supplier.pk)
        self.assertEqual(job.runner, 'browser')
        with self.assertRaises(CollectionStopped):
            start_job('shopbase', self.user.pk)

    def test_browser_launch_uses_private_stdin_not_command_line_or_database(self):
        import tempfile
        from unittest.mock import Mock
        self.supplier.website = 'https://shopbasebd.com'; self.supplier.save(using='ecommerce')
        process = Mock()
        with tempfile.TemporaryDirectory() as root, override_settings(BASE_DIR=root), \
             patch('ecommerce.supplier_browser.subprocess.Popen',return_value=process) as launch:
            response = self.client.post(f'/api/ecommerce/admin/suppliers/{self.supplier.pk}/browser-collection/',
                {'username':'test-account','password':'synthetic-browser-secret'},format='json')
        self.assertEqual(response.status_code, 202)
        self.assertNotIn('synthetic-browser-secret',str(launch.call_args.args))
        self.assertFalse(launch.call_args.kwargs['shell'])
        self.assertIn('synthetic-browser-secret', process.stdin.write.call_args.args[0])
        self.assertNotIn('synthetic-browser-secret',str(response.data))
        self.assertNotIn('synthetic-browser-secret',str(SupplierJob.objects.using('ecommerce').get().payload))
        self.supplier.refresh_from_db(using='ecommerce')
        self.assertEqual(self.supplier.credentials_ciphertext,'')

    def test_browser_navigation_refuses_internal_and_foreign_origins(self):
        from .supplier_browser import BrowserCollector, CollectionStopped
        collector = BrowserCollector('shopbase',None,'test','synthetic')
        for url in ('http://shopbasebd.com/store/products/all','https://127.0.0.1/a','https://evil.example/a','javascript:void(0)', 'https:///bad','https://shopbasebd.com:8443/private'):
            with self.assertRaises(CollectionStopped):
                collector.safe_url(url)
        self.assertEqual(collector.safe_url('/store/products/all'),'https://shopbasebd.com/store/products/all')

    def test_browser_check_reuses_connections_and_honours_cancellation(self):
        from .supplier_browser import BrowserCollector, start_job, CollectionStopped
        self.supplier.website = 'https://shopbasebd.com'; self.supplier.save(using='ecommerce')
        job = start_job('shopbase', self.user.pk)
        collector = BrowserCollector('shopbase',job,'test','synthetic')
        with patch('ecommerce.supplier_browser.time.monotonic',return_value=100), \
             patch('ecommerce.supplier_browser.close_old_connections') as close:
            collector.check(); collector.check(); collector.check()
            close.assert_called_once()
        SupplierJob.objects.using('ecommerce').filter(pk=job.pk).update(status='cancel_requested')
        with self.assertRaises(CollectionStopped):
            collector.check()

    def test_browser_fills_missing_price_only_with_explicit_opt_in(self):
        from .supplier_browser import BrowserCollector, amount
        self.assertIsNone(amount('-Tk100'))
        self.assertIsNone(amount('Tk100 - Tk200'))
        self.assertEqual(amount('W: ৳১,১৫০'),'1150.00')
        job = SupplierJob.objects.using('ecommerce').create(supplier=self.supplier,runner='browser',action='collect',status='running')
        collector = BrowserCollector('shopbase',job,'test','synthetic',report=lambda *a,**kw:None)
        item = {'id':'browser-id','title':'Public product','url':'https://shopbasebd.com/store/products/1','price':None}
        collector.capture([item],item['url'])
        offer = SupplierOffer.objects.using('ecommerce').get()
        self.assertIsNone(offer.source_price)
        item['price']='77.00'; collector.seen.clear()
        collector.capture([item],item['url'])
        offer.refresh_from_db(using='ecommerce'); self.assertIsNone(offer.source_price)
        collector.fill_missing_prices=True; collector.seen.clear()
        collector.capture([item],item['url'])
        offer.refresh_from_db(using='ecommerce'); self.assertEqual(offer.source_price,Decimal('77'))
        item['price']='99.00'; collector.seen.clear()
        collector.capture([item],item['url'])
        offer.refresh_from_db(using='ecommerce'); self.assertEqual(offer.source_price,Decimal('77'))
        self.assertFalse(Product.objects.using('ecommerce').exists())
        job.refresh_from_db(using='ecommerce'); self.assertEqual(job.processed,4)

    def test_selfshop_authentication_indicator_is_checked_after_form_submission(self):
        from unittest.mock import Mock
        from .supplier_browser import BrowserCollector, By
        collector = BrowserCollector('selfshop',None,'test','synthetic')
        collector.driver=Mock(); collector.driver.current_url='https://selfshop.com.bd/'
        collector.goto=Mock(); collector.check=Mock(); collector.challenge=Mock()
        trigger, password, form, phone, submit = (Mock() for _ in range(5))
        submit.text='Log in'
        phone.get_attribute.side_effect=lambda key: {'type':'text','name':'phone','placeholder':'Phone'}.get(key)
        password.find_elements.side_effect=lambda by,selector: [form] if 'ancestor::form' in selector else []
        form.find_elements.side_effect=lambda by,selector: [phone] if selector=='input' else [submit]
        submitted=[]
        submit.click.side_effect=lambda:submitted.append(True)
        collector.driver.find_elements.side_effect=lambda by,selector: [trigger] if 'Hello, Sign in' in selector else ([] if submitted else [password])
        def check_signed_in(script):
            self.assertTrue(submitted, 'Do not wait for an authenticated indicator before submitting the login form')
            self.assertIn('/dashboard/settings',script)
            return True
        collector.dom=Mock(side_effect=check_signed_in)
        with patch('ecommerce.supplier_browser.WebDriverWait') as wait:
            wait.return_value.until.side_effect=lambda fn:fn(collector.driver)
            collector.login()
        phone.send_keys.assert_called_once_with('test')
        password.send_keys.assert_called_once_with('synthetic')
        submit.click.assert_called_once()
        collector.dom.assert_called_once()

    def test_browser_pagination_reacquires_stale_next_button(self):
        from unittest.mock import Mock
        from selenium.common.exceptions import StaleElementReferenceException
        from .supplier_browser import BrowserCollector
        collector=BrowserCollector('selfshop',None,'test','synthetic'); collector.check=Mock()
        collector.driver=Mock(); old,new=Mock(),Mock()
        old.click.side_effect=StaleElementReferenceException('Synthetic stale button')
        collector.driver.find_elements.side_effect=[[old],[new]]
        self.assertTrue(collector.click_next_button())
        new.click.assert_called_once()

    def test_browser_category_enrichment_never_overwrites_existing_categories(self):
        from .supplier_browser import BrowserCollector
        job=SupplierJob.objects.using('ecommerce').create(supplier=self.supplier,runner='browser',action='collect',status='running')
        collector=BrowserCollector('shopbase',job,'test','synthetic',report=lambda *a,**kw:None)
        item={'id':'category-id','title':'Real source product','url':'https://shopbasebd.com/store/products/1','price':'20'}
        collector.capture([item],item['url'])
        collector.fill_missing_categories=True;collector.seen.clear()
        item['category']='Real category'; collector.capture([item],item['url'])
        offer=SupplierOffer.objects.using('ecommerce').get()
        self.assertEqual(offer.identity['category'],'Real category')
        self.assertEqual(offer.source_price,Decimal('20'))
        collector.seen.clear(); item['category']='Different category'
        collector.capture([item],item['url']);offer.refresh_from_db(using='ecommerce')
        self.assertEqual(offer.identity['category'],'Real category')
        self.assertEqual(offer.state,'needs_review')

    def test_split_source_emoji_does_not_drop_a_product_identity(self):
        from .supplier_browser import BrowserCollector
        job=SupplierJob.objects.using('ecommerce').create(supplier=self.supplier,runner='browser',action='collect',status='running')
        collector=BrowserCollector('shopbase',job,'test','synthetic',report=lambda *a,**kw:None)
        collector.capture([{'id':'unicode-id','title':'Broken emoji \ud83d','url':'https://shopbasebd.com/store/products/1','price':'20'}], 'https://shopbasebd.com/store/products/1')
        offer=SupplierOffer.objects.using('ecommerce').get()
        self.assertEqual(offer.external_id,'unicode-id')
        self.assertEqual(offer.title,'Broken emoji \ufffd')
        self.assertEqual(collector.counts['source_title_unicode_repaired'],1)

    def test_resellkori_estimated_profit_or_retail_is_never_a_source_cost(self):
        from .supplier_browser import BrowserCollector
        job=SupplierJob.objects.using('ecommerce').create(supplier=self.supplier,runner='browser',action='collect',status='running')
        collector=BrowserCollector('resellkori',job,'test','synthetic',report=lambda *a,**kw:None)
        collector.capture([{'id':'profit-id','title':'Service retail price','url':'https://resellkori.com/product/service','price':'3000'}], 'https://resellkori.com/products/')
        self.assertIsNone(SupplierOffer.objects.using('ecommerce').get().source_price)

    def test_browser_jobs_are_bounded_and_never_overlap_for_the_same_source(self):
        from .supplier_browser import start_job,CollectionStopped
        self.supplier.website='https://shopbasebd.com';self.supplier.save(using='ecommerce')
        start_job('shopbase',self.user.pk)
        Supplier.objects.using('ecommerce').create(name='Second approved source',website='https://www.dropifybd.com',enabled=True,terms_confirmed=True,terms_note='Owner-authorised test catalogue')
        start_job('dropify',self.user.pk)
        Supplier.objects.using('ecommerce').create(name='Third approved source',website='https://selfshop.com.bd',enabled=True,terms_confirmed=True,terms_note='Owner-authorised test catalogue')
        with self.assertRaises(CollectionStopped):start_job('selfshop',self.user.pk)
        self.assertEqual(SupplierJob.objects.using('ecommerce').count(),2)
