from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from cheradip.membership import refresh_membership
from cheradip.models import Customer, CustomerToken, CreatedQuestionSet, PackagePlan, PackageSubscription
from cheradip.package_service import activate_plan, current_subscription, process_subscription_renewal, subsource_allowed


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

    def test_job_seeker_uses_unique_question_metric(self):
        user = self.customer('job-user', acctype='JobSeeker')
        CreatedQuestionSet.objects.create(customer=user, name='Set', questions=[
            {'qid': f'j-{index}', 'question': f'Question {index}'} for index in range(100)
        ])
        progress = refresh_membership(user)
        self.assertEqual(progress.metric_name, 'questions_created')
        self.assertEqual(progress.base, 'Q > 99')
        self.assertEqual(progress.badge, 'Gold')


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

    def test_same_plan_is_not_charged_and_downgrade_is_free(self):
        starter = PackagePlan.objects.get(code='starter-academic')
        basic = PackagePlan.objects.get(code='basic-academic')
        first, balance, created, _ = activate_plan(self.user, basic)
        self.assertTrue(created)
        charged_balance = balance
        same, same_balance, created, message = activate_plan(self.user, basic)
        self.assertFalse(created)
        self.assertEqual(same.id, first.id)
        self.assertEqual(same_balance, charged_balance)
        self.assertIn('Already activated', message)
        lower, lower_balance, created, _ = activate_plan(self.user, starter)
        self.assertTrue(created)
        self.assertEqual(lower.payable_amount, 0)
        self.assertEqual(lower_balance, charged_balance)
        first.refresh_from_db()
        self.assertEqual(first.status, 'superseded')

    def test_failed_renewal_enters_grace_without_duplicate_charge(self):
        plan = PackagePlan.objects.get(code='starter-academic')
        now = timezone.now()
        row = PackageSubscription.objects.create(
            customer=self.user, plan=plan, status='active', plan_price=plan.price,
            payable_amount=plan.price, starts_at=now - timedelta(days=40),
            ends_at=now - timedelta(seconds=1), next_renewal_at=now - timedelta(seconds=1),
        )
        self.user.settings = {'balance': 0}
        self.user.save(update_fields=['settings'])
        process_subscription_renewal(row, now)
        row.refresh_from_db()
        self.assertEqual(row.status, 'grace')
        self.assertEqual(row.renewal_failed_attempts, 1)
        process_subscription_renewal(row, now + timedelta(hours=1))
        row.refresh_from_db()
        self.assertEqual(row.renewal_failed_attempts, 1)

    def test_successful_renewal_keeps_the_previous_period_as_history(self):
        plan = PackagePlan.objects.get(code='starter-academic')
        now = timezone.now()
        old = PackageSubscription.objects.create(
            customer=self.user, plan=plan, status='active', plan_price=plan.price,
            payable_amount=plan.price, starts_at=now - timedelta(days=40),
            ends_at=now - timedelta(seconds=1), next_renewal_at=now - timedelta(seconds=1),
        )
        renewed = process_subscription_renewal(old, now)
        old.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(old.status, 'expired')
        self.assertNotEqual(renewed.id, old.id)
        self.assertEqual(renewed.status, 'active')
        self.assertEqual(self.user.settings['balance'], 350)
        self.assertEqual(PackageSubscription.objects.filter(customer=self.user).count(), 2)

    def test_question_track_classification(self):
        self.assertTrue(subsource_allowed('academic', ''))
        self.assertTrue(subsource_allowed('academic', "MSB'24"))
        self.assertFalse(subsource_allowed('academic', "DU'24"))
        self.assertTrue(subsource_allowed('admission', "DU'24"))
        self.assertFalse(subsource_allowed('admission', "CB'23"))

    def test_free_student_access_lasts_one_month_plus_seven_days(self):
        plan = PackagePlan.objects.get(code='free-academic')
        now = timezone.now()
        row = PackageSubscription.objects.create(
            customer=self.user, plan=plan, status='active', plan_price=0,
            payable_amount=0, starts_at=now - timedelta(days=36),
            ends_at=now - timedelta(days=6), next_renewal_at=now - timedelta(days=6),
            auto_renew=False,
        )
        self.assertEqual(current_subscription(self.user, now).id, row.id)
        self.assertIsNone(current_subscription(self.user, now + timedelta(days=2)))
        row.refresh_from_db()
        self.assertEqual(row.status, 'expired')

    def test_active_student_package_unlock_is_temporary_and_free(self):
        plan = PackagePlan.objects.get(code='free-academic')
        now = timezone.now()
        PackageSubscription.objects.create(
            customer=self.user, plan=plan, status='active', plan_price=0,
            payable_amount=0, starts_at=now, ends_at=now + timedelta(days=30),
            next_renewal_at=now + timedelta(days=30), auto_renew=False,
        )
        response = self.client.post('/api/token/unlock_questions/', {
            'items': [{'qid': '01_01_0001', 'is_cq': False}],
        }, format='json', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['package_access'])
        self.assertEqual(response.data['debited'], 0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 500)
        self.assertNotIn('unlocked_question_qids', self.user.settings)
