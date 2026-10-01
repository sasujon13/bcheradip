from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIRequestFactory
from unittest.mock import patch

from cheradip.models import Customer, CustomerToken
from cheradip.student_views import (
    StudentExamResultsView,
    StudentLeaderboardView,
    StudentReportView,
    StudentStatsView,
)
from cheradip.exam_attempts import ATTEMPTS_KEY


class StudentDashboardApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.customer = Customer.objects.create_user(
            username='01700000000', password='test-password', fullName='Test Student',
            acctype='Student', group='Science', settings={},
        )
        self.token = CustomerToken.objects.create(key='student-test-token', customer=self.customer)
        self.scorer = patch('cheradip.student_views._score_exam_submission', side_effect=self.score_exam)
        self.scorer.start()
        self.addCleanup(self.scorer.stop)

    def score_exam(self, set_id, answers):
        scores = {12: (8, 10), 5: (1, 2), 99: (5, 10)}
        correct, total = scores.get(set_id, (6 + set_id, 10))
        return {
            'correct': correct, 'total': total, 'score': round(correct * 100 / total),
            'grading': {}, 'setName': 'Verified exam', 'setKey': 'verified',
            'examType': 'topic', 'examMode': 'regular', 'examVariant': '',
            'subjectTr': 'Physics 1st Paper', 'levelTr': 'Higher Secondary',
            'classLevel': '11-12',
        }

    def request(self, method, path, data=None):
        if method == 'post' and isinstance(data, dict) and data.get('attemptId'):
            self.customer.refresh_from_db()
            settings = dict(self.customer.settings or {})
            results = settings.get('student_exam_results', [])
            known = {str(row.get('attemptId') or '') for row in results if isinstance(row, dict)}
            if str(data['attemptId']) not in known:
                settings[ATTEMPTS_KEY] = [{
                    'attemptId': str(data['attemptId']),
                    'setId': int(data.get('setId') or 0),
                    'startedAt': timezone.now().isoformat(),
                    'expiresAt': (timezone.now() + timedelta(minutes=20)).isoformat(),
                }]
                self.customer.settings = settings
                self.customer.save(update_fields=['settings'])
        maker = getattr(self.factory, method)
        return maker(path, data or {}, format='json', HTTP_AUTHORIZATION='Bearer student-test-token')

    def test_result_submission_feeds_stats_report_and_leaderboard(self):
        result = {
            'attemptId': 'attempt-1', 'setId': 12, 'setName': 'Physics set',
            'score': 100, 'correct': 10, 'total': 10, 'answers': {'q1': 'ক'},
            'subjectTr': 'Physics 1st Paper', 'levelTr': 'Higher Secondary',
            'classLevel': '11-12', 'examType': 'topic', 'at': '2026-09-29T10:00:00+06:00',
        }
        response = StudentExamResultsView.as_view()(self.request('post', '/api/student/exam-results/', result))
        self.assertEqual(response.status_code, 201)

        stats = StudentStatsView.as_view()(self.request('get', '/api/student/stats/'))
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.data['examsCompleted'], 1)
        self.assertEqual(stats.data['averageScore'], 80)
        self.assertEqual(stats.data['questionsAnswered'], 10)
        self.assertEqual(stats.data['correctAnswers'], 8)

        report = StudentReportView.as_view()(self.request('get', '/api/student/reports/?period=all-time'))
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.data['totalExams'], 1)
        self.assertEqual(report.data['subjectBreakdown'][0]['name'], 'Physics 1st Paper')

        leaderboard = StudentLeaderboardView.as_view()(
            self.request('get', '/api/student/leaderboard/?period=all-time&group=S')
        )
        self.assertEqual(leaderboard.status_code, 200)
        self.assertEqual(leaderboard.data['user_rank'], 1)
        self.assertTrue(leaderboard.data['leaderboard'][0]['is_current_user'])

    def test_duplicate_attempt_is_idempotent(self):
        data = {
            'attemptId': 'same-attempt', 'setId': 5, 'score': 50,
            'correct': 2, 'total': 2, 'answers': {'q1': 'ক'}, 'at': '2026-09-29T10:00:00+06:00',
        }
        view = StudentExamResultsView.as_view()
        self.assertEqual(view(self.request('post', '/', data)).status_code, 201)
        duplicate = view(self.request('post', '/', data))
        self.assertEqual(duplicate.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(len(self.customer.settings['student_exam_results']), 1)

    def test_legacy_bulk_scores_are_rejected(self):
        results = []
        for index, exam_type in enumerate(('subject', 'chapter', 'topic'), 1):
            results.append({
                'attemptId': 'bulk-%s' % exam_type,
                'setId': index,
                'setName': '%s exam' % exam_type,
                'score': 60 + index * 10,
                'correct': 6 + index,
                'total': 10,
                'subjectTr': 'Physics 1st Paper',
                'levelTr': 'Higher Secondary',
                'classLevel': '11-12',
                'examType': exam_type,
                'at': '2026-09-2%sT10:00:00+06:00' % (6 + index),
            })
        response = StudentExamResultsView.as_view()(
            self.request('post', '/api/student/exam-results/', {'results': results})
        )
        self.assertEqual(response.status_code, 400)

    def test_invented_and_expired_attempts_are_rejected(self):
        payload = {
            'attemptId': 'invented', 'setId': 12, 'answers': {'q1': 'ক'},
        }
        direct = self.factory.post('/', payload, format='json', HTTP_AUTHORIZATION='Bearer student-test-token')
        invalid = StudentExamResultsView.as_view()(direct)
        self.assertEqual(invalid.status_code, 400)

        self.customer.refresh_from_db()
        settings = dict(self.customer.settings or {})
        settings[ATTEMPTS_KEY] = [{
            'attemptId': 'expired',
            'setId': 12,
            'startedAt': (timezone.now() - timedelta(hours=1)).isoformat(),
            'expiresAt': (timezone.now() - timedelta(minutes=1)).isoformat(),
        }]
        self.customer.settings = settings
        self.customer.save(update_fields=['settings'])
        expired_payload = {'attemptId': 'expired', 'setId': 12, 'answers': {'q1': 'ক'}}
        expired_request = self.factory.post(
            '/', expired_payload, format='json', HTTP_AUTHORIZATION='Bearer student-test-token'
        )
        expired = StudentExamResultsView.as_view()(expired_request)
        self.assertEqual(expired.status_code, 400)
        self.assertIn('expired', expired.data['error'].lower())

    def test_dashboard_apis_require_authentication(self):
        response = StudentStatsView.as_view()(self.factory.get('/api/student/stats/'))
        self.assertIn(response.status_code, (401, 403))

    def test_client_score_and_completed_flags_cannot_override_server(self):
        forged = {
            'attemptId': 'forged-attempt', 'setId': 99, 'score': 100,
            'correct': 10, 'total': 10, 'examType': 'chapter', 'answers': {'q1': 'ক'},
            'completed': False, 'at': '2026-09-29T10:00:00+06:00',
        }
        saved = StudentExamResultsView.as_view()(
            self.request('post', '/api/student/exam-results/', forged)
        )
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.data['result']['score'], 50)
        self.assertEqual(saved.data['result']['correct'], 5)
        self.assertTrue(saved.data['result']['completed'])
        self.assertNotEqual(saved.data['result']['at'], forged['at'])

        stats = StudentStatsView.as_view()(self.request('get', '/api/student/stats/'))
        self.assertEqual(stats.data['examsCompleted'], 1)
        self.assertEqual(stats.data['questionsAnswered'], 10)
