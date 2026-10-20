"""Access roles stay on Customer and only existing administrators can grant them."""
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase
from unittest.mock import patch

from cheradip.admin import import_csv_json_view_for_model
from cheradip.models import Customer, CustomerToken
from cheradip.admin_access import CustomerCreationForm, CustomerPasswordChangeForm


class CustomerAdminAccessTests(TestCase):
    def setUp(self):
        self.manager = admin.site._registry[Customer]
        self.administrator = Customer.objects.create_superuser(username='role-admin-test', password='test-only', fullName='Administrator')
        self.staff = Customer.objects.create_user(username='role-staff-test', password='test-only', fullName='Staff', is_staff=True)
        self.customer = Customer.objects.create_user(username='role-user-test', password='test-only', fullName='Customer')
        self.factory = RequestFactory()

    def request(self, user):
        request = self.factory.get('/admin/cheradip/customer/')
        request.user = user
        return request

    def test_administrator_sees_explicit_access_controls_on_same_customer_form(self):
        request = self.request(self.administrator)
        form = self.manager.get_form(request, self.customer)
        self.assertEqual(form.base_fields['is_staff'].label, 'Staff access')
        self.assertEqual(form.base_fields['is_superuser'].label, 'Administrator — full access')
        self.assertIn('user_permissions', form.base_fields)
        self.assertIn('Administration & marketplace access', [title for title, _ in self.manager.get_fieldsets(request, self.customer)])
        self.assertEqual(self.manager.account_role(self.administrator), 'Administrator')
        self.assertEqual(self.manager.account_role(self.staff), 'Staff')
        self.assertEqual(self.manager.account_role(self.customer), 'Customer')
        self.assertEqual(Customer._meta.db_table, 'cheradip_customers')
        self.client.force_login(self.administrator)
        with patch.object(admin.site, 'get_app_list', return_value=[]):
            response = self.client.get(f'/admin/cheradip/customer/{self.customer.pk}/change/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff access')
        self.assertContains(response, 'Administrator — full access')

    def test_staff_with_customer_edit_permission_cannot_promote_users(self):
        content_type = ContentType.objects.get_for_model(Customer)
        permission, _ = Permission.objects.get_or_create(content_type=content_type, codename='change_customer', defaults={'name': 'Can change customer'})
        self.staff.user_permissions.add(permission)
        form = self.manager.get_form(self.request(self.staff), self.customer)
        for field in ['is_staff', 'is_superuser', 'groups', 'user_permissions', 'password', 'settings']:
            self.assertNotIn(field, form.base_fields)

    def test_administrator_checkbox_enables_required_staff_flag(self):
        self.customer.is_superuser = True
        self.customer.is_staff = False
        self.manager.save_model(self.request(self.administrator), self.customer, None, True)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_superuser)
        self.assertTrue(self.customer.is_staff)

    def test_staff_cannot_import_privileged_customer_rows(self):
        from django.core.exceptions import PermissionDenied
        request = self.factory.post('/admin/cheradip/customer/import-csv-json/')
        request.user = self.staff
        with self.assertRaises(PermissionDenied):
            import_csv_json_view_for_model(Customer)(request)

    def test_access_entries_are_visible_under_the_cheradip_database(self):
        from backend.admin_app_list import get_app_list_by_database
        with patch('backend.table_activity.refresh_external_markers'), patch('backend.admin_app_list._table_notification_count', return_value=0):
            apps = get_app_list_by_database(self.request(self.administrator), app_label='cheradip')
        entries = {row['name']: row['admin_url'] for app in apps for row in app['models']}
        self.assertEqual(entries['Users & customers'], '/admin/cheradip/customer/')
        self.assertEqual(entries['User groups'], '/admin/auth/group/')
        self.assertEqual(entries['User permissions'], '/admin/auth/permission/')

    def test_native_user_creation_hashes_password_in_the_existing_customer_table(self):
        form = CustomerCreationForm(data={
            'username': 'new-role-user', 'fullName': 'Example Customer', 'acctype': 'Others',
            'usable_password': 'true', 'password1': 'TestOnly!7359Password', 'password2': 'TestOnly!7359Password',
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.check_password('TestOnly!7359Password'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.password, 'TestOnly!7359Password')

    def test_superuser_can_assign_and_remove_groups_and_individual_customer_permissions(self):
        content_type = ContentType.objects.get_for_model(Customer)
        view, _ = Permission.objects.get_or_create(content_type=content_type, codename='view_customer', defaults={'name': 'Can view customer'})
        change, _ = Permission.objects.get_or_create(content_type=content_type, codename='change_customer', defaults={'name': 'Can change customer'})
        group = Group.objects.create(name='Customer support test')
        group.permissions.add(view)
        self.client.force_login(self.administrator)
        payload = {'username': self.customer.username, 'fullName': self.customer.fullName, 'acctype': 'Student',
                   'is_active': 'on', 'is_staff': 'on', 'groups': [group.pk], 'user_permissions': [change.pk], '_save': 'Save'}
        with patch.object(admin.site, 'get_app_list', return_value=[]):
            response = self.client.post(f'/admin/cheradip/customer/{self.customer.pk}/change/', payload, HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 302, getattr(response, 'context_data', None))
        user = Customer.objects.get(pk=self.customer.pk)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_perm('cheradip.view_customer'))
        self.assertTrue(user.has_perm('cheradip.change_customer'))
        payload['groups'] = []
        payload['user_permissions'] = []
        with patch.object(admin.site, 'get_app_list', return_value=[]):
            response = self.client.post(f'/admin/cheradip/customer/{user.pk}/change/', payload, HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 302)
        user = Customer.objects.get(pk=user.pk)
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.user_permissions.exists())

    def test_group_and_permission_create_edit_delete_are_available_only_to_superusers(self):
        self.client.force_login(self.administrator)
        content_type = ContentType.objects.get_for_model(Customer)
        with patch.object(admin.site, 'get_app_list', return_value=[]):
            response = self.client.post('/admin/auth/permission/add/', {'name': 'Manage test access', 'content_type': content_type.pk, 'codename': 'manage_test_access', '_save': 'Save'}, HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(response.status_code, 302)
            permission = Permission.objects.get(content_type=content_type, codename='manage_test_access')
            response = self.client.post(f'/admin/auth/permission/{permission.pk}/change/', {'name': 'Changed test access', 'content_type': content_type.pk, 'codename': 'manage_test_access', '_save': 'Save'}, HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(response.status_code, 302)
            permission.refresh_from_db()
            self.assertEqual(permission.name, 'Changed test access')
            response = self.client.post('/admin/auth/group/add/', {'name': 'Test business role', 'permissions': [permission.pk], '_save': 'Save'}, HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(response.status_code, 302)
            group = Group.objects.get(name='Test business role')
            self.assertTrue(group.permissions.filter(pk=permission.pk).exists())
            response = self.client.post(f'/admin/auth/group/{group.pk}/change/', {'name': 'Changed business role', 'permissions': [], '_save': 'Save'}, HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(response.status_code, 302)
            group.refresh_from_db()
            self.assertEqual(group.name, 'Changed business role')
            self.assertFalse(group.permissions.exists())
            self.assertEqual(self.client.post(f'/admin/auth/group/{group.pk}/delete/', {'post': 'yes'}, HTTP_X_FORWARDED_PROTO='https').status_code, 302)
            self.assertEqual(self.client.post(f'/admin/auth/permission/{permission.pk}/delete/', {'post': 'yes'}, HTTP_X_FORWARDED_PROTO='https').status_code, 302)
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())
        self.assertFalse(Permission.objects.filter(pk=permission.pk).exists())
        for model in [Group, Permission]:
            manager = admin.site._registry[model]
            request = self.request(self.staff)
            self.assertFalse(manager.has_add_permission(request))
            self.assertFalse(manager.has_change_permission(request))
            self.assertFalse(manager.has_delete_permission(request))

    def test_staff_cannot_edit_delete_or_reset_an_administrator(self):
        request = self.request(self.staff)
        self.assertFalse(self.manager.has_change_permission(request, self.administrator))
        self.assertFalse(self.manager.has_delete_permission(request, self.administrator))
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            self.manager.user_change_password(request, str(self.administrator.pk))

    def test_admin_password_form_hashes_and_revokes_old_website_tokens(self):
        CustomerToken.objects.create(key='test-old-session', customer=self.customer)
        form = CustomerPasswordChangeForm(self.customer, data={
            'usable_password': 'true', 'password1': 'TestOnly!8296NewPassword', 'password2': 'TestOnly!8296NewPassword',
        })
        self.assertTrue(form.is_valid(), form.errors)
        with patch('cheradip.ext_account_sync.sync_customer_to_ext') as mirror:
            changed = form.save()
        self.assertTrue(changed.check_password('TestOnly!8296NewPassword'))
        self.assertFalse(CustomerToken.objects.filter(customer=changed).exists())
        mirror.assert_called_once()
