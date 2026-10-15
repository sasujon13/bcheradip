from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from cheradip.models import Customer, CustomerToken, PackagePlan, TrxManagement, VerificationChallenge, WalletOperation
from cheradip.serializers import InstitutesSerializer
from cheradip.student_views import _answer_key


class RemainingAuditPureTests(SimpleTestCase):
    def test_numeric_option_text_wins_over_ambiguous_option_number(self):
        self.assertEqual(_answer_key('2', ['0', '1', '2', '3']), 'গ')
        self.assertEqual(_answer_key('option_2', ['0', '1', '2', '3']), 'খ')

    def test_staff_without_order_change_permission_cannot_modify_orders(self):
        from ecommerce.models import Order
        from ecommerce.permissions import IsCommerceAdmin
        user = SimpleNamespace(is_authenticated=True, is_staff=True, is_superuser=False, has_perm=lambda _code: False)
        request = SimpleNamespace(user=user, method='PATCH')
        self.assertFalse(IsCommerceAdmin().has_permission(request, SimpleNamespace(permission_model=Order)))

    def test_inventory_and_csv_writes_require_both_relevant_model_permissions(self):
        from ecommerce.permissions import IsCommerceAdmin
        from ecommerce.views import AdminCsvImportView, AdminInventoryView
        granted = {'ecommerce.add_product', 'ecommerce.add_inventorymovement'}
        user = SimpleNamespace(
            is_authenticated=True, is_staff=True, is_superuser=False,
            has_perm=lambda code: code in granted,
        )
        request = SimpleNamespace(user=user, method='POST')
        permission = IsCommerceAdmin()
        self.assertFalse(permission.has_permission(request, AdminCsvImportView()))
        self.assertFalse(permission.has_permission(request, AdminInventoryView()))
        granted.update({'ecommerce.change_product', 'ecommerce.change_productvariant'})
        self.assertTrue(permission.has_permission(request, AdminCsvImportView()))
        self.assertTrue(permission.has_permission(request, AdminInventoryView()))

    def test_public_institute_serialization_includes_institution_contact(self):
        from cheradip.models import Institutes
        row = Institutes(eiinNo='100005', instituteName='School', mobile='01700000000', email='school@example.test')
        guest = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        payload = InstitutesSerializer(row, context={'request': guest}).data
        self.assertEqual(payload['instituteName'], 'School')
        self.assertEqual(payload['mobile'], '01700000000')
        self.assertEqual(payload['email'], 'school@example.test')
        paid = SimpleNamespace(user=SimpleNamespace(
            is_authenticated=True, settings={'unlocked_ntrca_eiins_v2': ['100005']},
        ))
        paid_payload = InstitutesSerializer(row, context={'request': paid}).data
        self.assertEqual(paid_payload['mobile'], '01700000000')


class RemainingAuditAccountTests(TransactionTestCase):
    databases = {'default'}

    def setUp(self):
        self.customer = Customer.objects.create_user(
            username='01711111111', password='old-password', fullName='Audit User',
            email='registered@example.test', settings={'balance': 0},
        )
        self.client = APIClient()
        self.client.credentials(HTTP_X_FORWARDED_PROTO='https')

    def test_recovery_refuses_new_contact_and_separates_code_purposes(self):
        response = self.client.post('/api/send_password_reset_code/', {
            'username': self.customer.username, 'email': 'attacker@example.test',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VerificationChallenge.objects.exists())

        with patch('cheradip.verification_service.verification_service.generate_code', return_value='123456'), patch(
            'cheradip.verification_service.verification_service.send_verification',
            return_value={'success': True, 'message': 'Sent', 'method': 'email'},
        ):
            sent = self.client.post('/api/send_password_reset_code/', {
                'username': self.customer.username, 'email': self.customer.email,
            }, format='json')
        self.assertEqual(sent.status_code, 200)
        self.assertNotEqual(VerificationChallenge.objects.get().code_hash, '123456')
        ordinary = self.client.post('/api/verify_code/', {
            'username': self.customer.username, 'code': '123456',
        }, format='json')
        self.assertEqual(ordinary.status_code, 400)
        with patch('cheradip.views.sync_customer_to_ext'):
            recovered = self.client.post('/api/reset_password_with_code/', {
                'username': self.customer.username, 'code': '123456', 'new_password': 'new-password',
            }, format='json')
        self.assertEqual(recovered.status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password('new-password'))
        self.assertFalse(VerificationChallenge.objects.exists())

    @override_settings(TRX_INGEST_SECRET='test-private-intake-key')
    def test_recharge_requires_trusted_intake_and_credits_once(self):
        payload = {
            'media': 'Nagad', 'received_amount': '10.00', 'currency': 'BDT',
            'sender_contact': '01711111111', 'trxid': 'AUDIT-RECHARGE-001',
            'transaction_date': '2026-10-12', 'transaction_time': '12:00', 'confidence': '0.95',
        }
        self.assertEqual(self.client.post('/api/trxid/', payload, format='json').status_code, 403)
        intake = self.client.post('/api/trxid/', payload, format='json', HTTP_X_CHERADIP_INGEST_KEY='test-private-intake-key')
        self.assertEqual(intake.status_code, 201, intake.data)
        self.assertTrue(TrxManagement.objects.get(pk=intake.data['id']).verified)
        self.assertEqual(self.client.post('/api/trxid/', payload, format='json', HTTP_X_CHERADIP_INGEST_KEY='test-private-intake-key').status_code, 200)
        token = CustomerToken.objects.create(key='audit-recharge-token', customer=self.customer)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}', HTTP_X_FORWARDED_PROTO='https')
        path = f"/api/token/{intake.data['id']}/update_status/"
        credited = self.client.post(path, {'trxid': payload['trxid']}, format='json')
        self.assertEqual(credited.status_code, 200, credited.data)
        self.assertEqual(self.client.post(path, {'trxid': payload['trxid']}, format='json').status_code, 409)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.settings['balance'], 1000)
        self.assertEqual(WalletOperation.objects.filter(operation_key='recharge:AUDIT-RECHARGE-001').count(), 1)

    def test_staff_can_open_manual_but_anonymous_cannot(self):
        self.customer.is_staff = True
        self.customer.save(update_fields=['is_staff'])
        self.client.force_login(self.customer)
        with override_settings(DEBUG=True):
            manual = self.client.get('/admin/manual/', HTTP_HOST='localhost:8000')
            self.assertEqual(manual.status_code, 200)
            self.assertContains(manual, 'http://localhost:4200/scrape')
            self.assertContains(self.client.get('/admin/', HTTP_HOST='localhost:8000'), 'http://localhost:4200/scrape')
            self.assertContains(self.client.get('/admin/manual/', HTTP_HOST='127.0.0.1:8000'),
                                'http://127.0.0.1:4200/scrape')
        with override_settings(DEBUG=False):
            self.assertContains(self.client.get('/admin/manual/'), 'href="/scrape"')
        self.client.logout()
        self.assertEqual(self.client.get('/admin/manual/', HTTP_X_FORWARDED_PROTO='https').status_code, 302)

    def test_exhausted_teacher_allowance_cannot_be_refreshed_by_free_downgrade(self):
        from cheradip.package_service import activate_plan
        self.customer.settings = {'balance': 50000}
        self.customer.save(update_fields=['settings'])
        high = PackagePlan.objects.create(
            code='audit-high', name='High', track='academic', audience='teacher',
            list_price=100, price=100, question_limit=90, sort_order=5,
        )
        low = PackagePlan.objects.create(
            code='audit-low', name='Low', track='academic', audience='teacher',
            list_price=80, price=80, question_limit=45, sort_order=4,
        )
        current, _, _, _ = activate_plan(self.customer, high)
        current.questions_used = 90
        current.save(update_fields=['questions_used'])
        replacement, balance, _, _ = activate_plan(self.customer, low)
        self.assertEqual(replacement.payable_amount, Decimal('80'))
        self.assertEqual(replacement.questions_used, 0)
        self.assertEqual(balance, 32000)

    def test_ntrca_eiin_is_charged_once_and_client_settings_cannot_grant_another(self):
        self.customer.settings = {'balance': 100}
        self.customer.save(update_fields=['settings'])
        token = CustomerToken.objects.create(key='audit-ntrca-token', customer=self.customer)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}', HTTP_X_FORWARDED_PROTO='https')
        with patch('cheradip.views.Institutes.objects.filter') as institutes:
            institutes.return_value.exists.return_value = True
            first = self.client.post('/api/token/use_trx/', {'eiin': '100005'}, format='json')
            second = self.client.post('/api/token/use_trx/', {'eiin': '100005'}, format='json')
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual((first.data['remaining'], second.data['remaining']), (80, 80))
        injected = self.client.post('/api/customer_settings/', {
            'settings': {'unlocked_ntrca_eiins_v2': ['999999']},
        }, format='json')
        self.assertEqual(injected.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.settings['unlocked_ntrca_eiins_v2'], ['100005'])
