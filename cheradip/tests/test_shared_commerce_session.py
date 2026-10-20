from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient
from cheradip.models import Customer, CustomerToken
from cheradip.sso import COOKIE


@override_settings(ALLOWED_HOSTS=['testserver', 'cheradip.com'])
class SharedCommerceSessionTests(TransactionTestCase):
    databases = {'default'}

    def setUp(self):
        self.a = Customer.objects.create_user(username='account-a', password='test', fullName='Account A')
        self.b = Customer.objects.create_user(username='account-b', password='test', fullName='Account B')
        CustomerToken.objects.create(customer=self.a, key='token-a')
        CustomerToken.objects.create(customer=self.b, key='token-b')
        self.client = APIClient()
        self.client.credentials(HTTP_HOST='cheradip.com', HTTP_X_FORWARDED_PROTO='https', HTTP_AUTHORIZATION='Bearer token-a')
        self.client.cookies[COOKIE] = 'token-b'

    def test_cookie_probe_reconciles_shared_account_instead_of_stale_bearer(self):
        response = self.client.get('/api/session/?cookie_only=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['username'], 'account-b')
        self.assertEqual(response.json()['authToken'], 'token-b')

    def test_stale_tab_logout_does_not_revoke_other_shared_account(self):
        response = self.client.post('/api/session/', HTTP_ORIGIN='https://cheradip.com')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomerToken.objects.filter(key='token-a').exists())
        self.assertTrue(CustomerToken.objects.filter(key='token-b').exists())
        self.assertNotIn(COOKIE, response.cookies)

    def test_invalid_shared_cookie_is_reported_without_falling_back_to_stale_bearer(self):
        self.client.cookies[COOKIE] = 'expired-token'
        response = self.client.get('/api/session/?cookie_only=1')
        self.assertFalse(response.json()['loggedIn'])
        self.assertTrue(response.json()['sharedSessionPresent'])
