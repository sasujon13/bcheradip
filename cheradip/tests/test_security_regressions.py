from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from cheradip.models import Customer, CustomerToken, JsonData, Transaction, TrxManagement
from cheradip.views import (
    PasswordExistsView,
    PendingQuestionApproveView,
    SignupProfileView,
    TokenViewSet,
    _scraper_validate_remote_url,
    _scraper_without_secrets,
)


class SecurityRegressionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.customer = Customer.objects.create_user(
            username='01710000000', password='correct-password', fullName='Customer One'
        )
        self.other = Customer.objects.create_user(
            username='01720000000', password='other-password', fullName='Customer Two'
        )
        self.token = CustomerToken.objects.create(
            key='customer-security-token', customer=self.customer,
            expires_at=timezone.now() + timedelta(days=1),
        )

    def auth(self, method, path, data=None, token='customer-security-token'):
        request = getattr(self.factory, method)(path, data or {}, format='json')
        request.META['HTTP_AUTHORIZATION'] = 'Bearer %s' % token
        return request

    def test_expired_bearer_token_is_rejected_and_removed(self):
        self.token.expires_at = timezone.now() - timedelta(seconds=1)
        self.token.save(update_fields=['expires_at'])
        response = PasswordExistsView.as_view()(
            self.auth('post', '/api/password/', {'password': 'correct-password'})
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(CustomerToken.objects.filter(key='customer-security-token').exists())

    def test_password_check_requires_post_and_current_user(self):
        unauthenticated = PasswordExistsView.as_view()(
            self.factory.post('/api/password/', {'password': 'correct-password'}, format='json')
        )
        self.assertIn(unauthenticated.status_code, (401, 403))
        accepted = PasswordExistsView.as_view()(
            self.auth('post', '/api/password/', {'password': 'correct-password'})
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(accepted.data['exists'])
        method_not_allowed = PasswordExistsView.as_view()(
            self.auth('get', '/api/password/?password=correct-password')
        )
        self.assertEqual(method_not_allowed.status_code, 405)

    def test_profile_cannot_read_another_customer(self):
        response = SignupProfileView.as_view()(
            self.auth('get', '/api/signup_profile/?username=01720000000')
        )
        self.assertEqual(response.status_code, 403)

    def test_pending_approval_accepts_only_staff_bearer(self):
        denied = PendingQuestionApproveView.as_view()(
            self.auth('post', '/api/pending-question/approve/', {'id': 999})
        )
        self.assertEqual(denied.status_code, 403)

        staff = Customer.objects.create_user(
            username='01730000000', password='staff-password', fullName='Staff', is_staff=True
        )
        CustomerToken.objects.create(
            key='staff-security-token', customer=staff,
            expires_at=timezone.now() + timedelta(days=1),
        )
        accepted_auth = PendingQuestionApproveView.as_view()(
            self.auth('post', '/api/pending-question/approve/', {'id': 999}, token='staff-security-token')
        )
        self.assertEqual(accepted_auth.status_code, 404)

    def test_transaction_activation_is_bound_and_one_time(self):
        trx = TrxManagement.objects.create(
            media='Nagad', received_amount=Decimal('5.00'), currency='BDT',
            sender_contact='01700000000', trxid='TX-ONE-TIME',
            transaction_date='2026-10-01', transaction_time='10:00',
            confidence=Decimal('1.00000'), status=0, token=0,
        )
        view = TokenViewSet.as_view({'post': 'update_status'})
        wrong = view(self.auth('post', '/', {'trxid': 'WRONG'}), pk=trx.pk)
        self.assertEqual(wrong.status_code, 400)
        first = view(self.auth('post', '/', {'trxid': 'TX-ONE-TIME'}), pk=trx.pk)
        self.assertEqual(first.status_code, 200)
        second = view(self.auth('post', '/', {'trxid': 'TX-ONE-TIME'}), pk=trx.pk)
        self.assertEqual(second.status_code, 409)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.settings['balance'], 500)

    def test_scraper_url_validation_blocks_local_network_targets(self):
        for value in ('http://localhost/admin', 'http://127.0.0.1/', 'file:///etc/passwd'):
            with self.assertRaises(ValueError):
                _scraper_validate_remote_url(value)

    def test_order_json_requires_auth_and_uses_signed_in_identity(self):
        url = '/api/save_json_data/'
        denied = self.client.post(
            url, {'username': self.other.username}, content_type='application/json', secure=True
        )
        self.assertIn(denied.status_code, (401, 403))

        accepted = self.client.post(
            url,
            {'username': self.other.username, 'items': [{'id': 1}]},
            content_type='application/json',
            secure=True,
            HTTP_AUTHORIZATION='Bearer customer-security-token',
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(JsonData.objects.latest('id').data['username'], self.customer.username)

    def test_order_json_cannot_rebind_another_customers_payment(self):
        Transaction.objects.create(
            trxid='BOUND-TX', username=self.other.username, paidFrom='01700000000'
        )
        response = self.client.post(
            '/api/save_json_data/',
            {'trxid': 'BOUND-TX', 'paidFrom': '01700000000'},
            content_type='application/json',
            secure=True,
            HTTP_AUTHORIZATION='Bearer customer-security-token',
        )
        self.assertEqual(response.status_code, 403)

    def test_scraper_helper_removes_persisted_credentials_recursively(self):
        clean = _scraper_without_secrets({
            'libraries': {'site': {'username': 'safe', 'password': 'secret', 'bearerToken': 'token'}},
            'nested': [{'api_key': 'secret'}],
        })
        self.assertEqual(clean['libraries']['site']['username'], 'safe')
        self.assertNotIn('password', clean['libraries']['site'])
        self.assertNotIn('bearerToken', clean['libraries']['site'])
        self.assertEqual(clean['nested'][0], {})
