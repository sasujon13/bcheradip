from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.db import router
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from cheradip.models import Customer, RewardsWallet, WithdrawalRequest, PackagePlan, PackageSubscription, AdminTableEvent
from cheradip.views import BearerTokenAuthentication
from cheradip.exam_attempts import issue_or_resume, score_snapshot
from cheradip.question_access import question_key, bind_legacy
from cheradip.tutor_key_store import save_customer_tutor_settings
from backend.table_activity import acknowledge, unread_count
from django.core.exceptions import PermissionDenied


class AuditPureTests(SimpleTestCase):
    def test_shared_session_cookie_is_secure_http_only_and_first_party(self):
        from cheradip.sso import SharedSessionMiddleware, COOKIE
        from rest_framework.response import Response
        request = APIRequestFactory().get('/', secure=True, HTTP_HOST='cheradip.com')
        response = SharedSessionMiddleware(lambda _request: Response({'authToken': 'test-token'}))(request)
        cookie = response.cookies[COOKIE]
        self.assertTrue(cookie['secure'])
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['domain'], '.cheradip.com')
        self.assertEqual(cookie['samesite'], 'Lax')
    def test_anonymous_question_payload_hides_locked_answer(self):
        from cheradip.question_access import protect_questions
        rows = protect_questions(SimpleNamespace(is_authenticated=False), 'hsc', 'physics', [{'qid': '1', 'answer': 'secret', 'explanation': 'solution'}])
        self.assertEqual((rows[0]['answer'], rows[0]['explanation']), ('', ''))
        self.assertTrue(rows[0]['answer_locked'])

    def test_other_origins_cannot_use_cookie_auth(self):
        from cheradip.sso import trusted_request
        factory = APIRequestFactory()
        self.assertFalse(trusted_request(factory.post('/', HTTP_ORIGIN='https://cheradip.com.evil.example')))
        self.assertFalse(trusted_request(factory.post('/', HTTP_ORIGIN='http://cheradip.com')))
        self.assertTrue(trusted_request(factory.post('/', HTTP_ORIGIN='https://ecommerce.cheradip.com')))

    def test_router_isolates_every_model(self):
        self.assertFalse(router.allow_migrate('default', 'cheradip', model_name='subject'))
        self.assertTrue(router.allow_migrate('hsc', 'cheradip', model_name='subject'))
        self.assertFalse(router.allow_migrate('default', 'cheradip', model_name='pendingsubjectrequesthonours'))
        self.assertTrue(router.allow_migrate('honours', 'cheradip', model_name='pendingsubjectrequesthonours'))
        self.assertFalse(router.allow_migrate('honours', 'auth', model_name='permission'))
        self.assertFalse(router.allow_migrate('ailt', 'cheradip', model_name='customer'))

    def test_snapshot_grades_only_shown_questions(self):
        snapshot = {'questions': [{'qid': '1', 'option_1': 'Yes', 'answer': 'Yes'}], 'metadata': {'setName': 'Frozen'}}
        data, attempt = issue_or_resume({}, 1, 1200, snapshot)
        _, resumed = issue_or_resume(data, 1, 1200, {'questions': []})
        self.assertEqual(attempt, resumed)
        score = score_snapshot(snapshot, {'1': 'ক', 'unshown': 'ক'})
        self.assertEqual((score['total'], score['correct'], score['score']), (1, 1, 100))

    def test_legacy_paid_ids_bind_once_without_cross_subject_access(self):
        data = {'unlocked_question_qids': ['1']}
        first = bind_legacy(data, 'hsc', 'physics', [{'qid': '1'}])
        second = bind_legacy(data, 'hsc', 'bengali', [{'qid': '1'}])
        self.assertIn(question_key('hsc', 'physics', '1'), first)
        self.assertNotIn(question_key('hsc', 'bengali', '1'), second)


class AuditAccountTests(TransactionTestCase):
    databases = {'default'}

    def setUp(self):
        self.user = Customer.objects.create_user(username='audit-user', password='test-password', settings={'balance': 100000}, acctype='Teacher')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_withdrawal_reserves_main_coins_and_cancel_restores_once(self):
        RewardsWallet.objects.create(customer=self.user, available_taka='500.00')
        response = self.client.post('/api/wallet/rewards/', {'method': 'bkash', 'accountNumber': '01700000000', 'amountTaka': 500}, format='json')
        # Exercise the view directly if the public wallet URL differs.
        if response.status_code == 404:
            from cheradip.package_views import RewardsWalletView
            request = APIRequestFactory().post('/', {'method': 'bkash', 'accountNumber': '01700000000', 'amountTaka': 500}, format='json')
            from rest_framework.test import force_authenticate
            force_authenticate(request, self.user)
            response = RewardsWalletView.as_view()(request)
        self.assertEqual(response.status_code, 201, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 50000)
        row = WithdrawalRequest.objects.get(customer=self.user)
        self.assertEqual(row.reserved_coins, 50000)
        from cheradip.package_views import WithdrawalCancelView
        request = APIRequestFactory().post('/')
        from rest_framework.test import force_authenticate
        force_authenticate(request, self.user)
        self.assertEqual(WithdrawalCancelView.as_view()(request, pk=row.pk).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 100000)
        self.assertEqual(WithdrawalCancelView.as_view()(request, pk=row.pk).status_code, 400)

    def test_settings_cannot_grant_coins_or_answers(self):
        response = self.client.post('/api/customer_settings/', {'settings': {'balance': 9999999, 'unlocked_question_keys': ['fake'], 'export_format': 'docx'}}, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.settings['balance'], 100000)
        self.assertNotIn('unlocked_question_keys', self.user.settings)
        self.assertEqual(self.user.settings['export_format'], 'docx')

    def test_tutor_settings_preserve_latest_wallet_state(self):
        stale = Customer.objects.get(pk=self.user.pk)
        Customer.objects.filter(pk=self.user.pk).update(settings={'balance': 12345, 'other': 'keep'})
        save_customer_tutor_settings(stale, provider='cheradip', model='auto')
        self.user.refresh_from_db()
        self.assertEqual((self.user.settings['balance'], self.user.settings['other']), (12345, 'keep'))

    def test_table_events_are_acknowledged_per_staff_user(self):
        request = SimpleNamespace(user=self.user)
        self.assertGreater(unread_count(request, 'default', Customer._meta.db_table), 0)
        acknowledge(request, 'default', Customer._meta.db_table)
        self.assertEqual(unread_count(request, 'default', Customer._meta.db_table), 0)
        self.user.fullName = 'Changed'; self.user.save(update_fields=['fullName'])
        self.assertEqual(unread_count(request, 'default', Customer._meta.db_table), 1)

    def test_teacher_student_package_is_free_to_unlock_and_server_prices_cq(self):
        from cheradip.question_access import unlock_items
        with patch('cheradip.question_access.load_unlock_item', return_value=('hsc', 'physics', {'qid': 'cq', 'type': 'CQ', 'subsource': ''})), patch('cheradip.question_access.active_subscriptions', return_value=[]):
            payload, code = unlock_items(self.user, [{'qid': 'cq', 'is_cq': False}])
        self.assertEqual((code, payload['debited']), (200, 50))
        with patch('cheradip.question_access.load_unlock_item', return_value=('hsc', 'physics', {'qid': 'new-cq', 'type': 'CQ', 'subsource': ''})), patch('cheradip.question_access.active_subscriptions', return_value=[SimpleNamespace(plan=SimpleNamespace(track='academic'))]):
            payload, code = unlock_items(self.user, [{'qid': 'new-cq', 'is_cq': False}])
        self.assertEqual((code, payload['debited'], payload['package_access']), (200, 0, True))

    def test_staff_without_permissions_cannot_edit_customer_table(self):
        from backend.database_admin_views import _table_access
        request = APIRequestFactory().post('/', {'action': 'change'})
        request.user = self.user
        self.user.is_staff = True
        with self.assertRaises(PermissionDenied):
            _table_access(request, 'default', Customer._meta.db_table, edit=True)

    def test_shared_subdomain_cookie_restores_session_and_blocks_hostile_post(self):
        from cheradip.models import CustomerToken
        from cheradip.sso import COOKIE
        token = CustomerToken.objects.create(key='shared-test-session', customer=self.user)
        client = APIClient()
        client.cookies[COOKIE] = token.key
        response = client.get('/api/session/', secure=True, HTTP_HOST='cheradip.com', HTTP_ORIGIN='https://ecommerce.cheradip.com')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['loggedIn'])
        self.assertEqual(response.json()['authToken'], token.key)
        hostile = client.post('/api/customer_settings/', {'settings': {'export_format': 'pdf'}}, format='json', secure=True, HTTP_ORIGIN='https://evil.example')
        self.assertEqual(hostile.status_code, 401)

    def test_completed_exam_history_is_not_truncated_at_2000(self):
        from cheradip.models import StudentExamRecord
        from cheradip.student_views import _results
        StudentExamRecord.objects.bulk_create([
            StudentExamRecord(customer=self.user, attempt_id=f'history-{i}', payload={'attemptId': f'history-{i}', 'score': 50, 'total': 1, 'correct': 1})
            for i in range(2001)
        ])
        self.assertEqual(len(_results(self.user)), 2001)
