from datetime import timedelta
from unittest.mock import patch
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from cheradip.models import Customer, CustomerToken, LiveClass


class LiveClassTests(TestCase):
    def setUp(self):
        self.user = Customer.objects.create_user(username='live-class-test', password='test-only', fullName='Learner')
        CustomerToken.objects.create(key='live-class-test-token', customer=self.user)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer live-class-test-token', HTTP_X_FORWARDED_PROTO='https')
        self.now = timezone.now()

    def lesson(self, **kwargs):
        data = {'title': 'Physics live lesson', 'subject': 'Physics', 'starts_at': self.now + timedelta(hours=1),
                'ends_at': self.now + timedelta(hours=2), 'join_url': 'https://example.com/class', 'is_published': True}
        data.update(kwargs)
        return LiveClass.objects.create(**data)

    def test_schedule_requires_sign_in_and_has_an_honest_empty_state(self):
        self.assertEqual(self.client.get('/api/live-classes/', HTTP_X_FORWARDED_PROTO='https').status_code, 401)
        response = self.api.get('/api/live-classes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'classes': [], 'nextClass': None, 'timezone': 'Asia/Dhaka'})

    def test_schedule_excludes_unpublished_cancelled_finished_and_missing_links(self):
        visible = self.lesson()
        for overrides in [{'is_published': False}, {'status': 'cancelled'}, {'status': 'completed'},
                          {'starts_at': self.now - timedelta(hours=2), 'ends_at': self.now - timedelta(hours=1)}, {'join_url': ''}]:
            self.lesson(**overrides)
        result = self.api.get('/api/live-classes/').json()
        self.assertEqual([row['id'] for row in result['classes']], [visible.pk])
        self.assertEqual(result['nextClass']['id'], visible.pk)
        self.assertNotIn('created_by', result['classes'][0])

    def test_next_class_is_earliest_future_lesson_while_current_class_stays_listed(self):
        current = self.lesson(starts_at=self.now - timedelta(minutes=10), ends_at=self.now + timedelta(minutes=10))
        next_class = self.lesson()
        self.lesson(starts_at=self.now + timedelta(hours=3), ends_at=self.now + timedelta(hours=4))
        result = self.api.get('/api/live-classes/?limit=1').json()
        self.assertEqual(result['classes'][0]['id'], current.pk)
        self.assertEqual(result['nextClass']['id'], next_class.pk)
        self.assertEqual(self.api.get('/api/live-classes/?limit=bad').status_code, 400)
        self.assertEqual(self.api.post('/api/live-classes/', {}).status_code, 405)

    def test_admin_validation_prevents_invalid_times_and_unsafe_or_missing_join_links(self):
        for overrides in [{'ends_at': self.now}, {'join_url': ''}, {'join_url': 'javascript:alert(1)'}]:
            row = self.lesson(**overrides)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_admin_entry_requires_assigned_model_permissions_for_staff(self):
        manager = admin.site._registry[LiveClass]
        request = self.client.request().wsgi_request
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        request.user = self.user
        self.assertFalse(manager.has_add_permission(request))
        self.assertFalse(manager.has_change_permission(request))

    def test_admin_saves_entered_class_times_as_bangladesh_time(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])
        self.client.force_login(self.user)
        with patch.object(admin.site, 'get_app_list', return_value=[]):
            response = self.client.post('/admin/cheradip/liveclass/add/', {
                'title': 'Bangladesh time lesson', 'subject': 'Physics', 'starts_at_0': '2026-11-11', 'starts_at_1': '22:20:00',
                'ends_at_0': '2026-11-11', 'ends_at_1': '23:20:00', 'join_url': 'https://example.com/lesson',
                'status': 'scheduled', 'is_published': 'on', '_save': 'Save',
            }, HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 302, getattr(response, 'context_data', None))
        row = LiveClass.objects.get(title='Bangladesh time lesson')
        self.assertEqual(row.starts_at.hour, 16)
        self.assertEqual(row.starts_at.minute, 20)
        self.assertEqual(row.created_by, self.user)
        self.assertIn('11-Nov 10:20 PM', admin.site._registry[LiveClass].bangladesh_start(row))


class LoginLayoutTests(TestCase):
    def test_login_uses_requested_container_bounds_without_losing_auth_form(self):
        response = self.client.get('/admin/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'min-width: 16em !important;')
        self.assertContains(response, 'max-width: 48em !important;')
        self.assertContains(response, 'margin: 100px auto;')
        self.assertContains(response, 'width: 100%;')
        self.assertContains(response, 'id="id_username"')
