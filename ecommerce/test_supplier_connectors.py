"""Read-only connector contracts. Synthetic keys only; no external requests."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
import requests
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from cryptography.fernet import Fernet
from .supplier_connectors import collect, ConnectorError, PRODUCT_URL, RESTRICTED
from .supplier_crypto import encrypt, decrypt


class ConnectorTests(SimpleTestCase):
    def setUp(self):
        self.supplier = SimpleNamespace(connector='business_koro')
        self.product = {'id': 'P1', 'name': 'Test cable', 'costPrice': 100,
                        'inStock': True, 'description': 'Not collected', 'images': ['not-downloaded'],
                        'variants': [{'color': 'Black', 'size': None, 'inStock': True}]}

    def fetch(self, payload=None, status=200, **kwargs):
        response = Mock(status_code=status)
        response.iter_content.return_value = [json.dumps(payload or {'data': [self.product]}).encode()]
        session = Mock()
        session.get.return_value = response
        with patch('ecommerce.supplier_connectors.decrypt', return_value={'api_key': 'synthetic-test', 'domain': 'shop.example'}), \
             patch('ecommerce.supplier_connectors.requests.Session', return_value=session):
            result = collect(self.supplier, **kwargs)
        self.assertFalse(session.trust_env)
        self.assertEqual(session.get.call_args.args, (PRODUCT_URL,))
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
        self.assertEqual(session.get.call_args.kwargs['headers']['x-domain'], 'shop.example')
        session.close.assert_called_once()
        return result

    def test_lightweight_mapping_does_not_invent_quantity_weight_or_provenance(self):
        rows, stats = self.fetch()
        self.assertEqual(stats['source_products'], 1)
        self.assertEqual(rows[0]['source_price'], '100.00')
        self.assertEqual(rows[0]['availability'], 'in_stock')
        self.assertEqual(rows[0]['vendor_id'], 'not-provided')
        self.assertIsNone(rows[0]['quantity'])
        self.assertIsNone(rows[0]['weight_grams'])
        self.assertFalse(rows[0]['single_unit'])
        self.assertEqual(rows[0]['identity']['authenticity'], 'unverified')
        self.assertNotIn('description', rows[0])
        self.assertNotIn('images', rows[0])

    def test_variant_identifiers_are_stable_and_separate(self):
        first, _ = self.fetch()
        self.product['variants'].append({'color': 'White', 'inStock': False})
        rows, _ = self.fetch()
        self.assertEqual(first[0]['variant_id'], rows[0]['variant_id'])
        self.assertNotEqual(rows[0]['variant_id'], rows[1]['variant_id'])
        self.assertEqual(rows[1]['availability'], 'out_of_stock')

    def test_actual_source_category_and_unambiguous_quantity_are_retained(self):
        self.product['category']='  Electronics  '; self.product['stockQuantity']=12
        rows,_=self.fetch()
        self.assertEqual(rows[0]['identity']['category'],'Electronics')
        self.assertEqual(rows[0]['quantity'],12)
        self.product['variants'].append({'color':'White','inStock':True})
        rows,_=self.fetch()
        self.assertIsNone(rows[0]['quantity'])
        self.assertIsNone(rows[1]['quantity'])
        self.product['variants'][1]['stockQuantity']=3
        rows,_=self.fetch()
        self.assertEqual(rows[1]['quantity'],3)

    def test_restricted_and_invalid_rows_are_counted(self):
        rows, stats = self.fetch({'data': [self.product, dict(self.product, name='Nicotine vape'),dict(self.product,name='928 Stun Gun'),dict(self.product,name='26 Inch Self Defense Stick'), None]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats['restricted_skipped'], 3)
        self.assertEqual(stats['invalid_skipped'], 1)
        self.assertIsNone(RESTRICTED.search('Mini Body Massage Gun'))

    def test_unhandled_pagination_and_malformed_feeds_fail_closed(self):
        for payload in ({'data': [self.product], 'next': '/page2'}, {'products': []}, {'data': [{'id': 'bad'}]}):
            with self.assertRaises(ConnectorError):
                self.fetch(payload)

    def test_failed_access_never_exposes_response_or_credentials(self):
        for status in (302, 401, 403, 429, 500):
            with self.assertRaises(ConnectorError) as error:
                self.fetch(status=status)
            self.assertNotIn('synthetic-test', str(error.exception))

    def test_cancellation_stops_before_request(self):
        with patch('ecommerce.supplier_connectors.requests.Session') as session:
            with self.assertRaises(ConnectorError):
                collect(self.supplier, lambda: False)
        session.assert_not_called()

    def test_expired_credentials_never_make_a_request(self):
        self.supplier.credential_expires_at = timezone.now() - timedelta(seconds=1)
        with patch('ecommerce.supplier_connectors.requests.Session') as session:
            with self.assertRaises(ConnectorError):
                collect(self.supplier)
        session.assert_not_called()

    def test_timeout_is_not_stock_confirmation(self):
        with patch('ecommerce.supplier_connectors.decrypt', return_value={'api_key': 'synthetic-test'}), \
             patch('ecommerce.supplier_connectors.requests.Session') as factory:
            factory.return_value.get.side_effect = requests.Timeout('private diagnostic')
            with self.assertRaises(ConnectorError) as error:
                collect(self.supplier)
        self.assertNotIn('private diagnostic', str(error.exception))

    def test_credential_roundtrip_and_missing_key_fail_closed(self):
        with override_settings(COMMERCE_SUPPLIER_KEY=Fernet.generate_key().decode(), COMMERCE_SUPPLIER_KEY_FILE=''):
            ciphertext = encrypt({'api_key': 'synthetic-test'})
            self.assertNotIn('synthetic-test', ciphertext)
            self.assertEqual(decrypt(SimpleNamespace(credentials_ciphertext=ciphertext)), {'api_key': 'synthetic-test'})
        with override_settings(COMMERCE_SUPPLIER_KEY='', COMMERCE_SUPPLIER_KEY_FILE=''):
            with self.assertRaises(ValueError):
                encrypt({'api_key': 'synthetic-test'})
