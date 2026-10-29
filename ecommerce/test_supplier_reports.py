from django.utils import timezone
from rest_framework.test import APIClient
from cheradip.models import Customer, CustomerToken
from django.test import TransactionTestCase
from .models import (Category, Product, Supplier, SupplierOffer, SupplierRecollectionRun,
                     SupplierSourceProduct)


class SupplierReportsTests(TransactionTestCase):
    databases = {'default', 'ecommerce'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='report-staff', password='test-only', fullName='Report Staff')
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        CustomerToken.objects.create(key='report-test-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer report-test-token', HTTP_X_FORWARDED_PROTO='https')
        self.category = Category.objects.using('ecommerce').create(name='Reports', slug='reports-test')
        self.alpha = Supplier.objects.using('ecommerce').create(
            name='Alpha source', website='https://alpha.example', enabled=True,
            terms_confirmed=True, terms_note='Test recollection licence')
        self.beta = Supplier.objects.using('ecommerce').create(
            name='Beta source', website='https://beta.example', enabled=False,
            terms_confirmed=True, terms_note='Test recollection licence')
        run = SupplierRecollectionRun.objects.using('ecommerce').create(supplier=self.alpha, mode='full', status='completed')
        hosted_source = SupplierSourceProduct.objects.using('ecommerce').create(
            supplier=self.alpha, source_key='hosted', external_id='H1', url='https://alpha.example/h1',
            title='Hosted shirt', content_hash='a' * 64, observed_at=timezone.now(), last_run=run)
        SupplierSourceProduct.objects.using('ecommerce').create(
            supplier=self.alpha, source_key='unhosted', external_id='U1', url='https://alpha.example/u1',
            title='Unhosted shirt', content_hash='b' * 64, observed_at=timezone.now(), last_run=run)
        product = Product.objects.using('ecommerce').create(
            name='Hosted shirt', slug='hosted-shirt-report', category=self.category, status='active')
        SupplierOffer.objects.using('ecommerce').create(
            supplier=self.alpha, external_id='H1', vendor_id='v1', url=hosted_source.url, title=hosted_source.title,
            source_product=hosted_source, imported_product=product, state='ready')
        SupplierOffer.objects.using('ecommerce').create(
            supplier=self.alpha, external_id='B1', vendor_id='v1', url='https://alpha.example/b1', title='Blocked',
            state='blacklist')

    def test_reports_count_collected_hosted_unhosted_and_blacklisted(self):
        response = self.client.get('/api/ecommerce/admin/supplier-reports/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['totals'], {
            'suppliers': 2, 'collected': 2, 'hosted': 1, 'unhosted': 1, 'blacklisted': 1,
        })
        alpha = next(row for row in response.data['rows'] if row['supplier_name'] == 'Alpha source')
        self.assertEqual(alpha['collected'], 2)
        self.assertEqual(alpha['hosted'], 1)
        self.assertEqual(alpha['unhosted'], 1)
        self.assertEqual(alpha['blacklisted'], 1)
        beta = next(row for row in response.data['rows'] if row['supplier_name'] == 'Beta source')
        self.assertEqual((beta['collected'], beta['hosted'], beta['unhosted'], beta['blacklisted']), (0, 0, 0, 0))

    def test_reports_filter_one_supplier(self):
        response = self.client.get('/api/ecommerce/admin/supplier-reports/', {'supplier': self.beta.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['selected_supplier'], self.beta.pk)
        self.assertEqual(len(response.data['rows']), 1)
        self.assertEqual(response.data['totals']['suppliers'], 1)
        self.assertEqual(response.data['totals']['collected'], 0)

    def test_reports_require_staff_supplier_access(self):
        guest = APIClient()
        self.assertIn(guest.get('/api/ecommerce/admin/supplier-reports/').status_code, (401, 403))
