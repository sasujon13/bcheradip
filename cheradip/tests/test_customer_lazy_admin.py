import json
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core.management import call_command
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cheradip.admin_access import settings_revision
from cheradip.models import Customer


class CustomerLazyAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administrator = Customer.objects.create_superuser(username='lazy-admin', password='test-only', fullName='Admin')
        cls.staff = Customer.objects.create_user(username='lazy-staff', password='test-only', fullName='Staff', is_staff=True)
        cls.customer = Customer.objects.create_user(username='lazy-customer', password='test-only', fullName='Target',
            settings={'balance': 123456, 'private_marker': 'SETTINGS_NOT_IN_INITIAL_HTML'})
        cls.referrer = Customer.objects.create_user(username='lazy-referrer', password='test-only', fullName='Unchosen referrer name')

    def setUp(self):
        self.manager = admin.site._registry[Customer]
        self.url = reverse('admin:cheradip_customer_change', args=[self.customer.pk])
        self.settings_url = reverse('admin:cheradip_customer_settings_json', args=[self.customer.pk])
        self.client.force_login(self.administrator)
        apps = patch.object(admin.site, 'get_app_list', return_value=[])
        apps.start()
        self.addCleanup(apps.stop)

    def post(self, extra=None):
        data = {'username': self.customer.username, 'fullName': 'Target updated', 'acctype': 'Student', 'is_active': 'on', '_save': 'Save'}
        data.update(extra or {})
        return self.client.post(self.url, data, HTTP_X_FORWARDED_PROTO='https')

    def test_initial_form_does_not_fetch_settings_or_enumerate_referrers(self):
        request = RequestFactory().get(self.url)
        request.user = self.administrator
        obj = self.manager.get_object(request, str(self.customer.pk))
        form_class = self.manager.get_form(request, obj)
        with CaptureQueriesContext(connection) as queries:
            form = form_class(instance=obj)
            html = form.as_p()
        self.assertIn('settings', obj.get_deferred_fields())
        self.assertNotIn('SETTINGS_NOT_IN_INITIAL_HTML', html)
        self.assertNotIn('Unchosen referrer name', html)
        self.assertIn('admin-autocomplete', html)
        self.assertIn('Load Settings', html)
        customer_queries = [q['sql'] for q in queries if 'SELECT' in q['sql'] and 'FROM `cheradip_customers`' in q['sql']]
        self.assertEqual(customer_queries, [], customer_queries)

    def test_settings_endpoint_is_explicit_private_and_read_only(self):
        response = self.client.get(self.settings_url, HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['settings'], self.customer.settings)
        self.assertEqual(response.json()['revision'], settings_revision(self.customer.settings))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.client.post(self.settings_url, {}, HTTP_X_FORWARDED_PROTO='https').status_code, 405)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.settings_url, HTTP_X_FORWARDED_PROTO='https').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.settings_url, HTTP_X_FORWARDED_PROTO='https').status_code, 302)

    def test_saving_an_unopened_editor_preserves_settings(self):
        self.assertEqual(self.post().status_code, 302)
        current = Customer.objects.get(pk=self.customer.pk)
        self.assertEqual(current.settings, self.customer.settings)
        self.assertEqual(current.fullName, 'Target updated')

    def test_opened_settings_can_be_edited_using_normal_save(self):
        value = {**self.customer.settings, 'export_format': 'pdf'}
        response = self.post({'settings_editor_loaded': '1', 'settings_editor_revision': settings_revision(self.customer.settings),
                              'settings_editor': json.dumps(value)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Customer.objects.get(pk=self.customer.pk).settings, value)

    def test_newer_wallet_changes_are_not_overwritten_by_stale_edits(self):
        newer = {**self.customer.settings, 'balance': 654321}
        Customer.objects.filter(pk=self.customer.pk).update(settings=newer)
        value = {**self.customer.settings, 'export_format': 'pdf'}
        response = self.post({'settings_editor_loaded': '1', 'settings_editor_revision': settings_revision(self.customer.settings),
                              'settings_editor': json.dumps(value)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Settings changed since you opened them')
        self.assertEqual(Customer.objects.get(pk=self.customer.pk).settings, newer)

    def test_viewing_but_not_editing_settings_keeps_newer_wallet_data(self):
        newer = {**self.customer.settings, 'balance': 654321}
        Customer.objects.filter(pk=self.customer.pk).update(settings=newer)
        response = self.post({'settings_editor_loaded': '1', 'settings_editor_revision': settings_revision(self.customer.settings),
                              'settings_editor': json.dumps(self.customer.settings)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Customer.objects.get(pk=self.customer.pk).settings, newer)

    def test_referrers_are_searchable_and_self_referral_is_rejected(self):
        response = self.client.get(reverse('admin:autocomplete'), {'app_label': 'cheradip', 'model_name': 'customer',
            'field_name': 'referred_by', 'term': 'Unchosen referrer'}, HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r['id'] for r in response.json()['results']], [str(self.referrer.pk)])
        response = self.post({'referred_by': self.customer.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'An account cannot refer itself')

    def test_bad_json_does_not_save_and_stays_open_for_correction(self):
        response = self.post({'settings_editor_loaded': '1', 'settings_editor_revision': settings_revision(self.customer.settings),
                              'settings_editor': '{invalid json'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a valid JSON')
        self.assertContains(response, 'Hide Settings')
        self.assertEqual(Customer.objects.get(pk=self.customer.pk).settings, self.customer.settings)

    def test_deploy_metadata_creates_definitions_but_never_grants_access(self):
        content_type = ContentType.objects.get(app_label='cheradip', model='liveclass')
        Permission.objects.filter(content_type=content_type, codename='view_liveclass').delete()
        users_before = Customer.objects.count()
        grants_before = (Customer.user_permissions.through.objects.count(), Group.permissions.through.objects.count())
        call_command('ensure_admin_metadata', stdout=StringIO())
        self.assertFalse(Permission.objects.filter(content_type=content_type, codename='view_liveclass').exists())
        call_command('ensure_admin_metadata', apply_missing=True, stdout=StringIO())
        self.assertTrue(Permission.objects.filter(content_type=content_type, codename='view_liveclass').exists())
        self.assertEqual(Customer.objects.count(), users_before)
        self.assertEqual(grants_before, (Customer.user_permissions.through.objects.count(), Group.permissions.through.objects.count()))
        self.assertEqual(Customer.objects.get(pk=self.customer.pk).settings, self.customer.settings)
