from django.test import TransactionTestCase
from .test_suppliers import SupplierTests
from .models import SupplierOffer, SupplierResearchItem, Product
from .supplier_research import start, update, snapshot


class ResumableResearchTests(TransactionTestCase):
    databases={'default','ecommerce'}
    setUp=SupplierTests.setUp

    def seed(self):
        SupplierOffer.objects.using('ecommerce').bulk_create([SupplierOffer(supplier=self.supplier,
            external_id=str(n),vendor_id='supplier',title=f'Research product {n}',url='https://supplier.example/item',
            source_price=100,availability='in_stock') for n in range(5)])

    def test_pause_resume_preserves_identity_notes_and_next_batch_excludes_completed_work(self):
        self.seed();batch=start(self.user.pk,size=3);items=list(batch.items.all())
        update(self.user.pk,batch.pk,'pause',checkpoints=[{'id':items[0].pk,'note':'Checked source; model and warranty still unconfirmed.'}])
        resumed=start(self.user.pk,size=10)
        self.assertEqual(resumed.pk,batch.pk)
        self.assertEqual(resumed.items.count(),3)
        self.assertIn('unconfirmed',resumed.items.first().note)
        for item in items:
            update(self.user.pk,batch.pk,'finish',item.pk,'Insufficient exact-match evidence; hold. No assumptions made.')
        batch.refresh_from_db(using='ecommerce');self.assertEqual(batch.status,'completed')
        saved = snapshot(batch)
        self.assertIn('competitor_observations', saved['items'][0]['decision_result'])
        self.assertEqual(saved['items'][0]['decision_result']['competitor_observations'], [])
        second=start(self.user.pk,size=3)
        self.assertNotEqual(second.pk,batch.pk)
        self.assertEqual(second.items.count(),2)
        self.assertEqual(SupplierResearchItem.objects.using('ecommerce').count(),5)
        self.assertEqual(Product.objects.using('ecommerce').count(),0)

    def test_missing_source_cost_and_permanent_exclusion_are_not_researched_as_viable(self):
        self.seed()
        rows=SupplierOffer.objects.using('ecommerce').order_by('pk')
        rows.filter(pk=rows[0].pk).update(source_price=None)
        rows.filter(pk=rows[1].pk).update(excluded_reason='Safety hold',state='excluded')
        batch=start(self.user.pk,size=10)
        self.assertEqual(batch.items.count(),3)
        update(self.user.pk,batch.pk,'pause')
        with self.assertRaisesRegex(ValueError,'Resume'):
            update(self.user.pk,batch.pk,'save',batch.items.first().pk,'Cannot edit paused work.')

    def test_api_uses_granular_research_permission_and_bounded_batches(self):
        self.seed()
        self.assertEqual(self.client.post('/api/ecommerce/admin/supplier-research/',{'action':'start','size':11},format='json').status_code,400)
        response=self.client.post('/api/ecommerce/admin/supplier-research/',{'action':'start','size':1},format='json')
        self.assertEqual(response.status_code,200,response.data)
        saved=self.client.get('/api/ecommerce/admin/supplier-research/').data
        self.assertEqual(saved['batch']['id'],response.data['batch']['id'])
        self.assertFalse(saved['automatic_research']);self.assertFalse(saved['quota_access'])
        self.user.is_superuser=False;self.user.save()
        self.assertEqual(self.client.get('/api/ecommerce/admin/supplier-research/').status_code,403)
