from datetime import timedelta

from django.test import TestCase
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import Mock, patch

from cheradip.membership import refresh_membership
from cheradip.models import (
    Customer, CustomerToken, CreatedQuestionSet, PackagePlan, PackageSubscription,
    ReferralCommission, RewardsWallet, WithdrawalRequest,
)
from cheradip.package_service import (
    active_subscriptions,
    activate_plan,
    current_subscription,
    process_subscription_renewal,
    question_track_for_user,
    subsource_allowed,
)
from cheradip.serializers import CustomerSignupSerializer
from backend.admin_app_list import _table_notification_count
from cheradip.admin import approve_withdrawals, process_withdrawals, reject_withdrawals


class MembershipRulesTests(TestCase):
    def customer(self, username, acctype='Student', settings=None):
        return Customer.objects.create_user(
            username=username, password='test-password', fullName='Test User',
            acctype=acctype, settings=settings or {},
        )

    def grant_paid_plan(self, customer, code='starter-academic'):
        now = timezone.now()
        if customer.acctype in {'Teacher', 'JobSeeker'} and not code.startswith('teacher-'):
            code = f'teacher-{code}'
        plan = PackagePlan.objects.get(code=code)
        return PackageSubscription.objects.create(
            customer=customer, plan=plan, status='active', plan_price=plan.price,
            payable_amount=plan.price, starts_at=now - timedelta(seconds=1), ends_at=now + timedelta(days=30),
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
        self.grant_paid_plan(user)
        progress = refresh_membership(user, now=now)
        self.assertEqual(progress.badge, 'Gold')
        self.assertEqual(progress.discount_percent, 10)
        self.assertEqual(float(progress.passing_rate), 50)

        old = now - timedelta(days=91)
        user.settings['student_exam_results'] = [{'score': 60, 'at': old.isoformat()} for _ in range(100)]
        user.save(update_fields=['settings'])
        progress = refresh_membership(user, now=now)
        self.assertEqual(progress.badge, 'Star')
        self.assertEqual(progress.metric_count, 0)
        self.assertEqual(progress.raw_metric_count, 100)
        self.assertFalse(progress.maintenance_met)

    def test_teacher_counts_unique_questions(self):
        now = timezone.now()
        teacher = self.customer('teacher-1', acctype='Teacher')
        self.grant_paid_plan(teacher)
        questions = [{'qid': f'q-{index}', 'question': f'Question {index}'} for index in range(100)]
        CreatedQuestionSet.objects.create(customer=teacher, name='Set', questions=questions + questions[:5])
        progress = refresh_membership(teacher, now=now)
        self.assertEqual(progress.metric_count, 100)
        self.assertEqual(progress.badge, 'Gold')
        self.assertEqual(progress.discount_percent, 10)

    def test_inactive_platinum_drops_one_stage_then_next_question_advances(self):
        now = timezone.now()
        teacher = self.customer('teacher-plat', acctype='Teacher')
        self.grant_paid_plan(teacher, 'basic-academic')
        old_set = CreatedQuestionSet.objects.create(
            customer=teacher, name='Old set',
            questions=[{'qid': f'old-{index}', 'question': f'Question {index}'} for index in range(300)],
        )
        CreatedQuestionSet.objects.filter(pk=old_set.pk).update(created_at=now - timedelta(days=91))
        progress = refresh_membership(teacher, now=now)
        self.assertEqual(progress.badge, 'Gold+')
        self.assertEqual(progress.base, 'Q > 199')
        self.assertEqual(progress.raw_metric_count, 300)
        self.assertEqual(progress.metric_count, 200)

        CreatedQuestionSet.objects.create(
            customer=teacher, name='New question', questions=[{'qid': 'new-300', 'question': 'Next question'}],
        )
        progress = refresh_membership(teacher, now=now + timedelta(seconds=1))
        self.assertEqual(progress.raw_metric_count, 301)
        self.assertEqual(progress.metric_count, 201)
        self.assertEqual(progress.badge, 'Gold+')

    def test_job_seeker_uses_unique_question_metric(self):
        user = self.customer('job-user', acctype='JobSeeker')
        self.grant_paid_plan(user)
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
            settings={'balance': 50000},
        )
        token = CustomerToken.objects.create(key='package-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')

    def expire_default_packages(self, audience):
        active_subscriptions(self.user)
        PackageSubscription.objects.filter(
            customer=self.user,
            payment_reference__startswith=f'default-free:{audience}:',
        ).update(status='expired')

    def test_free_and_affordable_paid_plans_activate_from_wallet(self):
        free = self.client.post('/api/packages/subscribe/', {'planCode': 'free-academic'}, format='json', secure=True)
        self.assertEqual(free.status_code, 200)
        self.assertEqual(free.data['status'], 'active')

        paid = self.client.post('/api/packages/subscribe/', {'planCode': 'starter-academic'}, format='json', secure=True)
        self.assertEqual(paid.status_code, 201)
        self.assertEqual(paid.data['status'], 'active')
        self.assertTrue(paid.data['orderNumber'].startswith('PKG-'))
        self.assertEqual(paid.data['orderStatusLabel'], 'Order Completed')
        self.assertEqual(paid.data['remainingBalance'], 35000)
        self.assertEqual(PackageSubscription.objects.filter(customer=self.user).count(), 5)
        self.assertFalse(PackageSubscription.objects.filter(
            customer=self.user, plan__audience='student', plan__name='Free',
            status__in=['active', 'grace'],
        ).exists())
        self.assertEqual(PackageSubscription.objects.filter(
            customer=self.user, plan__audience='teacher', plan__name='Free',
            status='active',
        ).count(), 2)

        tracked = self.client.get(
            f"/api/ecommerce/track/{paid.data['orderNumber']}/",
            secure=True,
        )
        self.assertEqual(tracked.status_code, 200, tracked.data)
        self.assertEqual(tracked.data['kind'], 'package')
        self.assertEqual(tracked.data['status_label'], 'Order Completed')
        self.assertEqual(tracked.data['payment_status_label'], 'Paid')

    def test_paid_plan_consumes_reference_portion_before_other_wallet_value(self):
        RewardsWallet.objects.create(
            customer=self.user,
            available_taka='80.00',
            lifetime_earned_taka='80.00',
        )

        response = self.client.post(
            '/api/packages/subscribe/',
            {'planCode': 'starter-academic'},
            format='json',
            secure=True,
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['remainingBalance'], 35000)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 35000)
        self.assertEqual(RewardsWallet.objects.get(customer=self.user).available_taka, 0)

    def test_insufficient_wallet_balance_does_not_create_subscription(self):
        response = self.client.post('/api/packages/subscribe/', {'planCode': 'advanced-3-combined'}, format='json', secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'insufficient_balance')
        self.assertEqual(response.data['remaining'], 50000)
        self.assertFalse(PackageSubscription.objects.filter(customer=self.user).exists())

    def test_list_returns_seeded_matrix_and_progress(self):
        response = self.client.get('/api/packages/', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['plans']), 48)
        self.assertEqual(sum(plan['audience'] == 'student' for plan in response.data['plans']), 24)
        self.assertEqual(sum(plan['audience'] == 'teacher' for plan in response.data['plans']), 24)
        self.assertEqual(response.data['progress']['accountType'], 'Student')
        self.assertTrue(PackagePlan.objects.filter(code='advanced-3-combined', price=3240).exists())
        self.assertEqual(PackagePlan.objects.get(code='free-academic').duration_months, 1)
        self.assertEqual(PackagePlan.objects.get(code='teacher-free-academic').duration_months, 36)
        self.assertEqual(len(response.data['activeSubscriptions']), 4)

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

    def test_academic_and_admission_remain_active_together(self):
        academic = PackagePlan.objects.get(code='starter-academic')
        admission = PackagePlan.objects.get(code='starter-admission')
        first, _, _, _ = activate_plan(self.user, academic)
        second, balance, _, _ = activate_plan(self.user, admission)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, 'active')
        self.assertEqual(second.status, 'active')
        self.assertEqual(balance, 20000)
        self.assertEqual(question_track_for_user(self.user), 'combined')

    def test_combined_stops_individual_auto_renew_without_ending_paid_access(self):
        self.user.settings = {'balance': 100000}
        self.user.save(update_fields=['settings'])
        academic, _, _, _ = activate_plan(self.user, PackagePlan.objects.get(code='starter-academic'))
        admission, _, _, _ = activate_plan(self.user, PackagePlan.objects.get(code='starter-admission'))
        combined, balance, created, _ = activate_plan(self.user, PackagePlan.objects.get(code='starter-combined'))
        academic.refresh_from_db()
        admission.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(combined.status, 'active')
        self.assertEqual(academic.status, 'active')
        self.assertEqual(admission.status, 'active')
        self.assertFalse(academic.auto_renew)
        self.assertFalse(admission.auto_renew)
        self.assertEqual(balance, 47500)

        covered, same_balance, created, message = activate_plan(
            self.user, PackagePlan.objects.get(code='basic-academic')
        )
        self.assertFalse(created)
        self.assertEqual(covered.id, combined.id)
        self.assertEqual(same_balance, balance)
        self.assertIn('included', message)

    def test_teacher_package_quota_requires_repayment_after_limit(self):
        teacher = Customer.objects.create_user(
            username='teacher-quota', password='test-password', fullName='Teacher',
            acctype='Teacher', settings={'balance': 50000},
        )
        token = CustomerToken.objects.create(key='teacher-quota-token', customer=teacher)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')
        plan = PackagePlan.objects.get(code='teacher-starter-academic')
        first, _, _, _ = activate_plan(teacher, plan)
        self.assertEqual(first.question_limit_snapshot, 20)
        first.questions_used = 19
        first.save(update_fields=['questions_used'])

        questions = [
            {'qid': f'academic-{index}', 'question': f'Question {index}', 'subsource': "CB'25"}
            for index in range(20)
        ]
        saved = client.post('/api/created_question_sets/', {
            'name': 'Quota set', 'questions': questions,
        }, format='json', secure=True)
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.data['debited'], 0)
        first.refresh_from_db()
        # One MCQ batch consumes one creation unit, not twenty question rows.
        self.assertEqual(first.questions_used, 20)

        blocked = client.post('/api/created_question_sets/', {
            'name': 'Over quota',
            'questions': [{'qid': 'academic-21', 'question': 'Question 21', 'subsource': "CB'25"}],
        }, format='json', secure=True)
        self.assertEqual(blocked.status_code, 402)
        self.assertEqual(blocked.data['code'], 'package_question_limit_reached')

        replacement, balance, created, _ = activate_plan(teacher, plan)
        self.assertTrue(created)
        self.assertNotEqual(replacement.id, first.id)
        self.assertEqual(replacement.questions_used, 0)
        self.assertEqual(balance, 20000)

    def test_student_can_activate_teacher_package_separately(self):
        response = self.client.post(
            '/api/packages/subscribe/', {'planCode': 'teacher-starter-academic'},
            format='json', secure=True,
        )
        self.assertEqual(response.status_code, 201)
        row = PackageSubscription.objects.get(customer=self.user, plan__code='teacher-starter-academic')
        self.assertEqual(row.plan.audience, 'teacher')
        self.assertEqual(response.data['remainingBalance'], 35000)
        self.assertFalse(PackageSubscription.objects.filter(
            customer=self.user, plan__audience='teacher', plan__name='Free',
            status__in=['active', 'grace'],
        ).exists())
        self.assertEqual(PackageSubscription.objects.filter(
            customer=self.user, plan__audience='student', plan__name='Free',
            status='active',
        ).count(), 2)
        status_response = self.client.get('/api/packages/status/', secure=True)
        self.assertTrue(status_response.data['active'])
        self.assertEqual(status_response.data['teacherProgress']['badge'], 'Star')

        saved = self.client.post('/api/created_question_sets/', {
            'name': 'Student teacher entitlement',
            'questions': [
                {'qid': f'student-author-{index}', 'question': f'MCQ {index}',
                 'type': 'MCQ', 'subsource': "CB'25"}
                for index in range(12)
            ],
        }, format='json', secure=True)
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.data['debited'], 0)
        row.refresh_from_db()
        self.assertEqual(row.questions_used, 1)

    def test_student_receives_default_teacher_packages_without_coin_charge(self):
        activate_plan(self.user, PackagePlan.objects.get(code='free-academic'))
        saved = self.client.post('/api/created_question_sets/', {
            'name': 'Student coin authoring',
            'questions': [
                {'qid': 'student-mcq', 'question': 'MCQ', 'type': 'MCQ', 'subsource': "CB'25"},
                {'qid': 'student-cq', 'question': 'CQ', 'type': 'সৃজনশীল', 'subsource': "CB'25"},
            ],
        }, format='json', secure=True)
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.data['debited'], 0)
        self.assertEqual(saved.data['remaining'], 50000)

    def test_mixed_mcq_and_cq_use_two_teacher_package_units(self):
        teacher = Customer.objects.create_user(
            username='teacher-mixed', password='test-password', fullName='Teacher Mixed',
            acctype='Teacher', settings={'balance': 50000},
        )
        token = CustomerToken.objects.create(key='teacher-mixed-token', customer=teacher)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')
        row, _, _, _ = activate_plan(teacher, PackagePlan.objects.get(code='teacher-starter-combined'))
        questions = [
            *[{'qid': f'mixed-m-{index}', 'question': 'MCQ', 'type': 'MCQ', 'subsource': "CB'25"}
              for index in range(10)],
            *[{'qid': f'mixed-c-{index}', 'question': 'CQ', 'type': 'সৃজনশীল', 'subsource': "DU'25"}
              for index in range(3)],
        ]
        saved = client.post('/api/created_question_sets/', {
            'name': 'Mixed batch', 'questions': questions,
        }, format='json', secure=True)
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.data['debited'], 0)
        row.refresh_from_db()
        self.assertEqual(row.questions_used, 2)

    def test_failed_coin_fallback_rolls_back_reserved_package_units(self):
        self.user.settings = {'balance': 15000}
        self.user.save(update_fields=['settings'])
        row, _, _, _ = activate_plan(
            self.user, PackagePlan.objects.get(code='teacher-starter-academic')
        )
        PackageSubscription.objects.filter(
            customer=self.user, plan__code='teacher-free-admission', status='active',
        ).update(status='expired')
        self.user.settings = {'balance': 0}
        self.user.save(update_fields=['settings'])
        response = self.client.post('/api/created_question_sets/', {
            'name': 'Mixed tracks without coins',
            'questions': [
                {'qid': 'covered-academic', 'question': 'Academic', 'type': 'MCQ', 'subsource': "CB'25"},
                {'qid': 'uncovered-admission', 'question': 'Admission', 'type': 'MCQ', 'subsource': "DU'25"},
            ],
        }, format='json', secure=True)
        self.assertEqual(response.status_code, 400)
        row.refresh_from_db()
        self.assertEqual(row.questions_used, 0)
        self.assertFalse(CreatedQuestionSet.objects.filter(customer=self.user).exists())

    def test_pending_question_creation_also_uses_coin_guard(self):
        self.expire_default_packages('teacher')
        response = self.client.post('/api/pending_questions/submit/', {
            'level_tr': 'Higher Secondary', 'class_level': '11-12',
            'subject_tr': 'Physics 1st Paper', 'chapter': 'Chapter', 'topic': 'Topic',
            'question': 'A new MCQ', 'type': 'MCQ', 'subsource': "CB'25",
        }, format='json', secure=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['debited'], 25)
        self.assertEqual(response.data['remaining'], 49975)

    def test_teacher_package_renewal_uses_teacher_badge_discount_for_student(self):
        row, _, _, _ = activate_plan(
            self.user, PackagePlan.objects.get(code='teacher-starter-academic')
        )
        CreatedQuestionSet.objects.create(
            customer=self.user, name='Teacher badge work',
            questions=[{'qid': f'teacher-badge-{index}', 'question': 'Question'} for index in range(100)],
        )
        teacher_progress = refresh_membership(self.user, audience='teacher')
        student_progress = refresh_membership(self.user, audience='student')
        self.assertEqual(teacher_progress.badge, 'Gold')
        self.assertEqual(teacher_progress.discount_percent, 10)
        self.assertEqual(student_progress.badge, 'None')
        now = timezone.now()
        PackageSubscription.objects.filter(pk=row.pk).update(
            starts_at=now - timedelta(days=40),
            ends_at=now - timedelta(seconds=1),
            next_renewal_at=now - timedelta(seconds=1),
        )
        row.refresh_from_db()
        renewed = process_subscription_renewal(row, now)
        self.user.refresh_from_db()
        self.assertEqual(float(renewed.payable_amount), 135)
        self.assertEqual(renewed.badge_discount_percent, 10)
        self.assertEqual(self.user.settings['balance'], 21500)

    def test_teacher_can_buy_student_and_teacher_packages_independently(self):
        teacher = Customer.objects.create_user(
            username='teacher-dual', password='test-password', fullName='Teacher Dual',
            acctype='Teacher', settings={'balance': 60000},
        )
        student_plan = PackagePlan.objects.get(code='starter-academic')
        teacher_plan = PackagePlan.objects.get(code='teacher-starter-academic')
        student_subscription, first_balance, created, _ = activate_plan(teacher, student_plan)
        self.assertTrue(created)
        self.assertEqual(refresh_membership(teacher, audience='student').badge, 'Star')
        self.assertEqual(refresh_membership(teacher, audience='teacher').badge, 'None')
        teacher_subscription, second_balance, created, _ = activate_plan(teacher, teacher_plan)
        self.assertTrue(created)
        self.assertEqual(first_balance, 45000)
        self.assertEqual(second_balance, 30000)
        self.assertNotEqual(student_subscription.id, teacher_subscription.id)
        self.assertEqual(current_subscription(teacher, audience='student').id, student_subscription.id)
        self.assertEqual(current_subscription(teacher, audience='teacher').id, teacher_subscription.id)
        self.assertEqual(refresh_membership(teacher, audience='teacher').badge, 'Star')

    def test_job_seeker_can_activate_both_package_audiences(self):
        user = Customer.objects.create_user(
            username='job-dual', password='test-password', fullName='Job Dual',
            acctype='JobSeeker', settings={'balance': 60000},
        )
        student, _, created_student, _ = activate_plan(user, PackagePlan.objects.get(code='starter-admission'))
        teacher, balance, created_teacher, _ = activate_plan(
            user, PackagePlan.objects.get(code='teacher-starter-admission')
        )
        self.assertTrue(created_student)
        self.assertTrue(created_teacher)
        self.assertEqual(student.plan.audience, 'student')
        self.assertEqual(teacher.plan.audience, 'teacher')
        self.assertEqual(balance, 30000)

    def test_default_teacher_package_grants_teacher_question_quota(self):
        teacher = Customer.objects.create_user(
            username='teacher-st-only', password='test-password', fullName='Teacher Student Only',
            acctype='Teacher', settings={'balance': 50000},
        )
        subscription, _, _, _ = activate_plan(teacher, PackagePlan.objects.get(code='starter-academic'))
        self.assertEqual(subscription.question_limit_snapshot, 0)
        from cheradip.package_service import reserve_teacher_question_allowance
        questions = [{'qid': 'teacher-no-quota', 'question': 'Question', 'subsource': "CB'25"}]
        self.assertEqual(reserve_teacher_question_allowance(teacher, questions), [])

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
        self.assertEqual(self.user.settings['balance'], 35000)
        self.assertEqual(PackageSubscription.objects.filter(customer=self.user).count(), 2)

    def test_question_track_classification(self):
        self.assertTrue(subsource_allowed('academic', ''))
        self.assertTrue(subsource_allowed('academic', "MSB'24"))
        self.assertFalse(subsource_allowed('academic', "DU'24"))
        self.assertTrue(subsource_allowed('admission', "DU'24"))
        self.assertFalse(subsource_allowed('admission', "CB'23"))

    def test_default_student_free_access_lasts_one_month_plus_seven_days(self):
        now = timezone.now()
        rows = active_subscriptions(self.user, now=now)
        self.assertEqual(len(rows), 4)
        academic = next(row for row in rows if row.plan.code == 'free-academic')
        teacher_academic = next(row for row in rows if row.plan.code == 'teacher-free-academic')
        self.assertEqual(academic.plan.duration_months, 1)
        self.assertEqual(teacher_academic.plan.duration_months, 36)
        self.assertIsNotNone(current_subscription(
            self.user, academic.ends_at + timedelta(days=6),
            audience='student', track='academic',
        ))
        self.assertIsNone(current_subscription(
            self.user, academic.ends_at + timedelta(days=8),
            audience='student', track='academic',
        ))

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
        self.assertEqual(self.user.settings['balance'], 50000)
        self.assertNotIn('unlocked_question_qids', self.user.settings)

    def test_coin_unlock_is_remembered_and_never_charged_twice(self):
        self.expire_default_packages('student')
        payload = {'items': [{'qid': 'paid-01', 'is_cq': False}]}
        first = self.client.post('/api/token/unlock_questions/', payload, format='json', secure=True)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['debited'], 10)
        self.assertEqual(first.data['remaining'], 49990)
        second = self.client.post('/api/token/unlock_questions/', payload, format='json', secure=True)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['debited'], 0)
        self.assertEqual(second.data['remaining'], 49990)
        self.user.refresh_from_db()
        self.assertIn('paid-01', self.user.settings['unlocked_question_qids'])

    def test_referral_commission_uses_referrers_rv_and_coin_conversion(self):
        referrer = Customer.objects.create_user(
            username='referrer', password='test-password', fullName='Referrer',
            acctype='Student', settings={'balance': 0},
        )
        plan = PackagePlan.objects.get(code='starter-academic')
        now = timezone.now()
        PackageSubscription.objects.create(
            customer=referrer, plan=plan, status='active', plan_price=plan.price,
            payable_amount=plan.price, starts_at=now, ends_at=now + timedelta(days=30),
        )
        self.user.referred_by = referrer
        self.user.save(update_fields=['referred_by'])
        activate_plan(self.user, plan)
        referrer.refresh_from_db()
        commission = ReferralCommission.objects.get(referrer=referrer)
        self.assertEqual(commission.reference_value_percent, 20)
        self.assertEqual(commission.commission_coins, 3000)
        self.assertEqual(referrer.settings['balance'], 3000)
        rewards = RewardsWallet.objects.get(customer=referrer)
        self.assertEqual(float(rewards.available_taka), 30.0)
        self.assertEqual(float(rewards.lifetime_earned_taka), 30.0)

    def test_teacher_package_referral_uses_referrers_teacher_badge(self):
        referrer = Customer.objects.create_user(
            username='ref-teacher', password='test-password', fullName='Teacher Referrer',
            acctype='Student', settings={'balance': 0},
        )
        plan = PackagePlan.objects.get(code='teacher-starter-academic')
        now = timezone.now()
        PackageSubscription.objects.create(
            customer=referrer, plan=plan, status='active', plan_price=plan.price,
            payable_amount=plan.price, starts_at=now, ends_at=now + timedelta(days=30),
        )
        CreatedQuestionSet.objects.create(
            customer=referrer, name='Teacher badge questions',
            questions=[{'qid': f'ref-teacher-{index}', 'question': 'Question'} for index in range(100)],
        )
        self.assertEqual(refresh_membership(referrer, audience='teacher').reference_value_percent, 30)
        self.user.referred_by = referrer
        self.user.save(update_fields=['referred_by'])
        activate_plan(self.user, plan)
        commission = ReferralCommission.objects.get(referrer=referrer)
        referrer.refresh_from_db()
        self.assertEqual(commission.reference_value_percent, 30)
        self.assertEqual(commission.commission_coins, 4500)
        self.assertEqual(referrer.settings['balance'], 4500)

    def test_withdrawal_reserves_only_reference_balance_and_can_be_cancelled(self):
        RewardsWallet.objects.create(
            customer=self.user, available_taka=150, lifetime_earned_taka=150,
        )
        below_minimum = self.client.post('/api/wallet/', {
            'method': 'bkash', 'accountNumber': '01700000000', 'amountTaka': 99,
        }, format='json', secure=True)
        self.assertEqual(below_minimum.status_code, 400)

        created = self.client.post('/api/wallet/', {
            'method': 'bkash', 'accountNumber': '01700000000', 'amountTaka': 120,
        }, format='json', secure=True)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['wallet']['availableTaka'], 30.0)
        request_id = created.data['withdrawal']['id']
        self.assertEqual(_table_notification_count(connection, 'cheradip_withdrawal_requests'), 1)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 50000)

        too_large = self.client.post('/api/wallet/', {
            'method': 'nagad', 'accountNumber': '01700000000', 'amountTaka': 100,
        }, format='json', secure=True)
        self.assertEqual(too_large.status_code, 400)

        cancelled = self.client.post(
            f'/api/wallet/withdrawals/{request_id}/cancel/', {}, format='json', secure=True,
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data['wallet']['availableTaka'], 150.0)
        self.assertEqual(WithdrawalRequest.objects.get(pk=request_id).status, 'cancelled')
        self.assertEqual(_table_notification_count(connection, 'cheradip_withdrawal_requests'), 0)

    def test_wallet_endpoint_returns_coins_reference_balance_and_methods(self):
        RewardsWallet.objects.create(customer=self.user, available_taka=120.50, lifetime_earned_taka=120.50)
        response = self.client.get('/api/wallet/', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['wallet']['coinBalance'], 50000)
        self.assertEqual(response.data['wallet']['availableTaka'], 120.5)
        self.assertEqual(response.data['wallet']['minimumWithdrawalTaka'], 100)
        self.assertEqual({row['value'] for row in response.data['methods']}, {'bkash', 'nagad', 'dbbl', 'sonali'})

    def test_admin_approval_records_paid_amount_and_rejection_refunds(self):
        admin_user = Customer.objects.create_superuser(
            username='wallet-admin', password='test-password', fullName='Wallet Admin',
        )
        wallet = RewardsWallet.objects.create(
            customer=self.user, available_taka=50, lifetime_earned_taka=250,
        )
        approved = WithdrawalRequest.objects.create(
            customer=self.user, method='bkash', account_number='01700000000',
            amount_taka=100, balance_before_taka=250, balance_after_taka=150,
        )
        rejected = WithdrawalRequest.objects.create(
            customer=self.user, method='nagad', account_number='01700000000',
            amount_taka=100, balance_before_taka=150, balance_after_taka=50,
        )
        request = Mock(user=admin_user)
        modeladmin = Mock()

        process_withdrawals(modeladmin, request, WithdrawalRequest.objects.filter(pk=approved.pk))
        approved.refresh_from_db()
        self.assertEqual(approved.status, 'processing')

        approve_withdrawals(modeladmin, request, WithdrawalRequest.objects.filter(pk=approved.pk))
        approved.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(approved.status, 'approved')
        self.assertEqual(approved.processed_by_id, admin_user.id)
        self.assertEqual(float(wallet.lifetime_withdrawn_taka), 100.0)

        reject_withdrawals(modeladmin, request, WithdrawalRequest.objects.filter(pk=rejected.pk))
        rejected.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(rejected.status, 'rejected')
        self.assertEqual(float(wallet.available_taka), 150.0)


class ReferralSignupTests(TestCase):
    def setUp(self):
        self.referrer = Customer.objects.create_user(
            username='01700000001', password='test-password', fullName='Referrer', acctype='Teacher'
        )

    def payload(self, username='01700000002', reference='01700000001'):
        return {'acctype': 'Student', 'fullName': 'New User', 'username': username,
                'password': 'Pass@123', 'reference': reference}

    def test_valid_reference_is_saved(self):
        serializer = CustomerSignupSerializer(data=self.payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.referred_by_id, self.referrer.id)

    def test_self_reference_is_rejected(self):
        serializer = CustomerSignupSerializer(data=self.payload('01700000003', '01700000003'))
        self.assertFalse(serializer.is_valid())
        self.assertIn('reference', serializer.errors)

    def test_unknown_reference_is_rejected(self):
        serializer = CustomerSignupSerializer(data=self.payload(reference='01799999999'))
        self.assertFalse(serializer.is_valid())
        self.assertIn('reference', serializer.errors)

    def test_others_account_type_uses_the_shared_customer_table(self):
        serializer = CustomerSignupSerializer(data=self.payload('01700000004'))
        serializer.initial_data['acctype'] = 'Others'
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.acctype, 'Others')

    def test_referral_summary_preserves_country_code_plus_sign(self):
        user = Customer.objects.create_user(
            username='+880170000001', password='test-password', fullName='Country Code', acctype='Teacher'
        )
        token = CustomerToken.objects.create(key='country-code-token', customer=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')
        response = client.get('/api/referrals/summary/', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['reference'], '+880170000001')
        self.assertEqual(response.data['referencePath'], '/auth?reference=%2B880170000001')

    @patch('cheradip.views.sync_customer_to_ext')
    def test_signup_endpoint_passes_reference_to_serializer(self, sync_mock):
        response = APIClient().post('/api/signup/', self.payload(), format='json', secure=True)
        self.assertEqual(response.status_code, 200, response.data)
        user = Customer.objects.get(username='01700000002')
        self.assertEqual(user.referred_by_id, self.referrer.id)
        sync_mock.assert_called_once()
