from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from cheradip.membership import refresh_membership
from cheradip.models import Customer, CustomerToken, CreatedQuestionSet, PackagePlan, PackageSubscription


class MembershipRulesTests(TestCase):
    def customer(self, username, acctype='Student', settings=None):
        return Customer.objects.create_user(
            username=username, password='test-password', fullName='Test User',
            acctype=acctype, settings=settings or {},
        )

    def test_student_gold_requires_exams_pass_rate_and_recent_activity(self):
        now = timezone.now()
        rows = ([{'score': 60, 'at': now.isoformat()} for _ in range(50)] +
                [{'score': 20, 'at': now.isoformat()} for _ in range(50)])
        user = self.customer('student-1', settings={
            'student_exam_results': rows,
            'membership_exam_lifetime_count': 100,
            'membership_exam_passed_count': 50,
        })
        progress = refresh_membership(user, now=now)
        self.assertEqual(progress.badge, 'Gold')
        self.assertEqual(progress.discount_percent, 10)
        self.assertEqual(float(progress.passing_rate), 50)

        old = now - timedelta(days=91)
        user.settings['student_exam_results'] = [{'score': 60, 'at': old.isoformat()} for _ in range(100)]
        user.save(update_fields=['settings'])
        progress = refresh_membership(user, now=now)
        self.assertEqual(progress.badge, 'Star')
        self.assertFalse(progress.maintenance_met)

    def test_teacher_counts_unique_questions(self):
        now = timezone.now()
        teacher = self.customer('teacher-1', acctype='Teacher')
        questions = [{'qid': f'q-{index}', 'question': f'Question {index}'} for index in range(100)]
        CreatedQuestionSet.objects.create(customer=teacher, name='Set', questions=questions + questions[:5])
        progress = refresh_membership(teacher, now=now)
        self.assertEqual(progress.metric_count, 100)
        self.assertEqual(progress.badge, 'Gold')
        self.assertEqual(progress.discount_percent, 10)


class PackageApiTests(TestCase):
    def setUp(self):
        self.user = Customer.objects.create_user(
            username='package-user', password='test-password', fullName='Package User', acctype='Student',
            settings={'balance': 500},
        )
        token = CustomerToken.objects.create(key='package-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')

    def test_free_and_affordable_paid_plans_activate_from_wallet(self):
        free = self.client.post('/api/packages/subscribe/', {'planCode': 'free-academic'}, format='json', secure=True)
        self.assertEqual(free.status_code, 201)
        self.assertEqual(free.data['status'], 'active')

        paid = self.client.post('/api/packages/subscribe/', {'planCode': 'starter-academic'}, format='json', secure=True)
        self.assertEqual(paid.status_code, 201)
        self.assertEqual(paid.data['status'], 'active')
        self.assertEqual(paid.data['remainingBalance'], 350)
        self.assertEqual(PackageSubscription.objects.filter(customer=self.user).count(), 2)

    def test_insufficient_wallet_balance_does_not_create_subscription(self):
        response = self.client.post('/api/packages/subscribe/', {'planCode': 'advanced-3-combined'}, format='json', secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'insufficient_balance')
        self.assertEqual(response.data['remaining'], 500)
        self.assertFalse(PackageSubscription.objects.filter(customer=self.user).exists())

    def test_list_returns_seeded_matrix_and_progress(self):
        response = self.client.get('/api/packages/', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['plans']), 24)
        self.assertEqual(response.data['progress']['accountType'], 'Student')
        self.assertTrue(PackagePlan.objects.filter(code='advanced-3-combined', price=3240).exists())
