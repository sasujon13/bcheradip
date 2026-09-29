from django.test import TestCase
from rest_framework.test import APIRequestFactory

from cheradip.models import Customer, CustomerToken
from cheradip.student_views import (
    StudentExamResultsView,
    StudentLeaderboardView,
    StudentReportView,
    StudentStatsView,
)


class StudentDashboardApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.customer = Customer.objects.create_user(
            username='01700000000', password='test-password', fullName='Test Student',
            acctype='Student', group='Science', settings={},
        )
        self.token = CustomerToken.objects.create(key='student-test-token', customer=self.customer)

    def request(self, method, path, data=None):
        maker = getattr(self.factory, method)
        return maker(path, data or {}, format='json', HTTP_AUTHORIZATION='Bearer student-test-token')

    def test_result_submission_feeds_stats_report_and_leaderboard(self):
        result = {
            'attemptId': 'attempt-1', 'setId': 12, 'setName': 'Physics set',
            'score': 80, 'correct': 8, 'total': 10,
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
            'correct': 1, 'total': 2, 'at': '2026-09-29T10:00:00+06:00',
        }
        view = StudentExamResultsView.as_view()
        self.assertEqual(view(self.request('post', '/', data)).status_code, 201)
        duplicate = view(self.request('post', '/', data))
        self.assertEqual(duplicate.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(len(self.customer.settings['student_exam_results']), 1)

    def test_bulk_sync_counts_every_exam_type(self):
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
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['added'], 3)

        stats = StudentStatsView.as_view()(self.request('get', '/api/student/stats/'))
        self.assertEqual(stats.data['examsCompleted'], 3)
        self.assertEqual(stats.data['questionsAnswered'], 30)
        self.assertEqual(stats.data['correctAnswers'], 24)

        duplicate = StudentExamResultsView.as_view()(
            self.request('post', '/api/student/exam-results/', {'results': results})
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.data['added'], 0)

    def test_dashboard_apis_require_authentication(self):
        response = StudentStatsView.as_view()(self.factory.get('/api/student/stats/'))
        self.assertIn(response.status_code, (401, 403))

    def test_unfinished_attempt_does_not_inflate_completed_stats(self):
        unfinished = {
            'attemptId': 'unfinished-attempt', 'setId': 99, 'score': 40,
            'correct': 4, 'total': 10, 'examType': 'chapter',
            'completed': False, 'at': '2026-09-29T10:00:00+06:00',
        }
        saved = StudentExamResultsView.as_view()(
            self.request('post', '/api/student/exam-results/', unfinished)
        )
        self.assertEqual(saved.status_code, 201)

        stats = StudentStatsView.as_view()(self.request('get', '/api/student/stats/'))
        self.assertEqual(stats.data['examsCompleted'], 0)
        self.assertEqual(stats.data['questionsAnswered'], 0)
        self.assertEqual(stats.data['currentRank'], 0)
