"""Validation and request-shape tests for browser tutor provider keys."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory

from cheradip import tutor_key_store, tutor_providers
from cheradip.models import Customer, CustomerToken
from cheradip.tutor_chat import TutorSettingsView


class TutorProviderTests(SimpleTestCase):
    def test_only_allowlisted_providers_are_accepted(self):
        self.assertEqual(
            tutor_providers.validate_provider_config(None),
            {'provider': 'cheradip', 'api_key': ''},
        )
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            tutor_providers.validate_provider_config(
                {'provider': 'custom', 'api_key': 'secret'})

    @patch('cheradip.tutor_providers.requests.post')
    def test_google_request_uses_the_selected_key_and_model(self, post):
        response = Mock()
        response.json.return_value = {
            'candidates': [{'content': {'parts': [{'text': 'Gemini answer'}]}}],
        }
        post.return_value = response
        text = tutor_providers.complete({
            'model': 'gemini-2.5-flash',
            'messages': [{'role': 'system', 'content': 'Teach.'},
                         {'role': 'user', 'content': 'Explain.'}],
            'file_context': [],
        }, {'provider': 'google', 'api_key': 'google-test-key'})
        self.assertEqual(text, 'Gemini answer')
        self.assertIn('gemini-2.5-flash:generateContent', post.call_args.args[0])
        self.assertNotIn('google-test-key', post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs['headers']['x-goog-api-key'], 'google-test-key')


class CustomerTutorKeyTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create_user(
            username='1700000000', password='test-pass', fullName='Tutor User')
        CustomerToken.objects.create(key='tutor-token', customer=self.customer)
        self.request = APIRequestFactory().post('/', {}, format='json',
                                                HTTP_AUTHORIZATION='Bearer tutor-token')

    def test_personal_key_is_encrypted_in_customer_json_and_can_be_resolved(self):
        tutor_key_store.save_customer_tutor_settings(
            self.customer, provider='openai', model='gpt-4.1-mini',
            api_keys={'openai': 'personal-test-key'})
        self.customer.refresh_from_db()
        stored = self.customer.settings['tutor_ai']['api_keys']['openai']
        self.assertTrue(stored.startswith('fernet:v1:'))
        self.assertNotIn('personal-test-key', stored)
        resolved = tutor_key_store.resolve_provider_config(
            self.request, {'provider': 'openai', 'api_key': ''})
        self.assertEqual(resolved['api_key'], 'personal-test-key')

    @patch('cheradip.tutor_key_store.database_provider_key', return_value='shared-test-key')
    def test_shared_database_key_is_used_when_customer_has_no_personal_key(self, shared):
        resolved = tutor_key_store.resolve_provider_config(
            self.request, {'provider': 'openai', 'api_key': ''})
        self.assertEqual(resolved['api_key'], 'shared-test-key')
        shared.assert_called_once_with('openai')

    @patch('cheradip.tutor_key_store.database_provider_key', return_value='')
    def test_settings_endpoint_saves_key_but_never_returns_it(self, _shared):
        factory = APIRequestFactory()
        response = TutorSettingsView.as_view()(factory.post('/', {
            'provider': 'openai', 'model': 'gpt-4.1-mini',
            'api_keys': {'openai': 'account-secret-key'},
        }, format='json', HTTP_AUTHORIZATION='Bearer tutor-token'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['key_status']['openai']['personal'])
        self.assertNotIn('account-secret-key', str(response.data))
        read = TutorSettingsView.as_view()(factory.get(
            '/', HTTP_AUTHORIZATION='Bearer tutor-token'))
        self.assertEqual(read.data['provider'], 'openai')
        self.assertNotIn('account-secret-key', str(read.data))
