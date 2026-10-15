from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from cheradip.models import Customer, CustomerToken, PackagePlan, PackageSubscription
from cheradip.package_service import active_subscriptions
from cheradip.unlock_entitlements import (
    INSTITUTE_EXPIRIES, INSTITUTE_KEYS, PACKAGE_INSTITUTES,
    effective_institute_eiins,
)


class UnlockAccessIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .package_fixtures import seed_test_plans
        seed_test_plans()

    def setUp(self):
        self.customer = Customer.objects.create_user(
            username='01712345678', password='test-password', fullName='Unlock Test',
            acctype='Student', settings={'balance': 100},
        )
        token = CustomerToken.objects.create(key='unlock-test-token', customer=self.customer)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')

    def paid_teacher_plan(self):
        plan = PackagePlan.objects.get(code='teacher-starter-academic')
        now = timezone.now()
        return PackageSubscription.objects.create(
            customer=self.customer, plan=plan, status='active', plan_price=plan.price,
            payable_amount=plan.price, starts_at=now - timedelta(seconds=1),
            ends_at=now + timedelta(days=30), auto_renew=False,
        )

    def unlock_institute(self):
        with patch('cheradip.views.Institutes.objects.filter') as institutes:
            institutes.return_value.exists.return_value = True
            return self.client.post('/api/token/use_trx/', {'eiin': '114770'}, format='json', secure=True)

    def test_paid_teacher_plan_unlocks_questions_and_institute_without_coins(self):
        active_subscriptions(self.customer)
        PackageSubscription.objects.filter(
            customer=self.customer, payment_reference__startswith='default-free:student:',
        ).update(status='expired')
        subscription = self.paid_teacher_plan()
        self.customer.settings = {'balance': 0}
        self.customer.save(update_fields=['settings'])
        question = {'qid': 'q1', 'type': 'MCQ', 'subsource': "DU'25"}
        with patch('cheradip.question_access.load_unlock_item', return_value=('hsc', 'physics', question)):
            response = self.client.post('/api/token/unlock_questions/', {
                'items': [{'qid': 'q1', 'level_tr': 'Higher Secondary',
                           'class_level': '11-12', 'subject_tr': 'Physics'}],
            }, format='json', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['package_access'])
        self.assertEqual(response.data['debited'], 0)
        institute = self.unlock_institute()
        self.assertEqual(institute.status_code, 200)
        self.assertTrue(institute.data['packageAccess'])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.settings['balance'], 0)
        self.assertIn('114770', self.customer.settings[PACKAGE_INSTITUTES])
        self.assertIn('114770', effective_institute_eiins(self.customer))
        subscription.status = 'expired'
        subscription.save(update_fields=['status'])
        self.assertNotIn('114770', effective_institute_eiins(self.customer))

    def test_expired_coin_institute_unlock_requires_new_payment(self):
        first = self.unlock_institute()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['remaining'], 80)
        self.customer.refresh_from_db()
        self.assertIn('114770', self.customer.settings[INSTITUTE_KEYS])
        data = dict(self.customer.settings)
        expiries = dict(data[INSTITUTE_EXPIRIES])
        expiries['114770'] = (timezone.now() - timedelta(seconds=1)).isoformat()
        data[INSTITUTE_EXPIRIES] = expiries
        self.customer.settings = data
        self.customer.save(update_fields=['settings'])
        second = self.unlock_institute()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['remaining'], 60)
