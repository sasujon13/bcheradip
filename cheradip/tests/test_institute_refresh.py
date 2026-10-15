from datetime import date, datetime, timezone as datetime_timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db import connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from cheradip.institute_refresh import (
    due_month_key, ensure_scheduled_run, process_one_public_refresh,
    process_scheduled_step, prune_old_update_records,
)
from cheradip.models import InstituteRefreshEvent, InstituteRefreshRequest, InstituteUpdateRun, Institutes


@override_settings(SECURE_SSL_REDIRECT=False)
class InstituteRefreshTests(TransactionTestCase):
    databases = {'default', 'job'}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connection = connections['job']
        cls.created_table = Institutes._meta.db_table not in connection.introspection.table_names()
        if cls.created_table:
            with connection.schema_editor() as editor:
                editor.create_model(Institutes)

    @classmethod
    def tearDownClass(cls):
        if cls.created_table:
            with connections['job'].schema_editor() as editor:
                editor.delete_model(Institutes)
        super().tearDownClass()

    def setUp(self):
        Institutes.objects.all().delete()
        Institutes.objects.create(eiinNo='100002', instituteName='Nayavizora School')
        self.client = APIClient()

    def test_public_visit_queues_once_and_reports_changed_result(self):
        url = '/api/institutes/100002/refresh/'
        self.assertEqual(self.client.get(url).data['status'], 'not_requested')
        queued = self.client.post(url, {}, format='json')
        self.assertEqual((queued.status_code, queued.data['status']), (202, 'queued'))
        self.assertEqual(self.client.post(url, {}, format='json').data['status'], 'queued')
        self.assertEqual(InstituteRefreshRequest.objects.count(), 1)
        with patch('cheradip.institute_refresh.process_institute_page', return_value={
            'failed': 0, 'records': [{'status': 'unchanged', 'emisWarning': ''}],
            'teachersCreated': 1,
        }):
            self.assertEqual(process_one_public_refresh(), '100002')
        status = self.client.get(url).data
        self.assertEqual(status['status'], 'complete')
        self.assertTrue(status['changed'])
        self.assertEqual(InstituteRefreshEvent.objects.filter(eiin='100002', status='complete').count(), 1)
        self.assertEqual(self.client.post(url, {}, format='json').data['status'], 'complete')
        self.assertIsNone(process_one_public_refresh())

    def test_public_refresh_rejects_nonlisted_eiin(self):
        self.assertEqual(self.client.post('/api/institutes/000000/refresh/', {}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/institutes/100003/refresh/', {}, format='json').status_code, 404)

    def test_last_day_and_recovery_window_are_dhaka_calendar_based(self):
        self.assertEqual(due_month_key(date(2028, 2, 29)), '2028-02')
        self.assertEqual(due_month_key(date(2028, 3, 1)), '2028-02')
        self.assertEqual(due_month_key(date(2028, 3, 3)), '2028-02')
        self.assertIsNone(due_month_key(date(2028, 3, 4)))
        self.assertIsNone(ensure_scheduled_run(date(2028, 3, 4)))
        first = ensure_scheduled_run(date(2028, 2, 29))
        self.assertEqual(first.schedule_month, '2028-02')
        self.assertEqual(first.total, 1)
        self.assertEqual(ensure_scheduled_run(date(2028, 3, 1)).pk, first.pk)

    def test_monthly_worker_continues_recent_staff_run_instead_of_duplication(self):
        manual = InstituteUpdateRun.objects.create(total=1)
        InstituteUpdateRun.objects.filter(pk=manual.pk).update(
            started_at=datetime(2028, 2, 28, 12, tzinfo=datetime_timezone.utc))
        scheduled = ensure_scheduled_run(date(2028, 2, 29))
        self.assertEqual(scheduled.pk, manual.pk)
        self.assertEqual(scheduled.schedule_month, '2028-02')
        self.assertEqual(InstituteUpdateRun.objects.count(), 1)

    def test_monthly_run_retries_failed_eiin_three_times_then_stops(self):
        with TemporaryDirectory() as directory, override_settings(INSTITUTE_UPDATE_LOG_ROOT=directory):
            run = ensure_scheduled_run(date(2028, 2, 29))
            calls = []

            def source(**kwargs):
                calls.append(kwargs['eiin'])
                return {'failed': 1, 'records': [{'status': 'failed', 'detail': 'Source unavailable'}]}

            with patch('cheradip.institute_update_runs.process_institute_page', side_effect=source):
                self.assertTrue(process_scheduled_step())  # First full pass.
                for round_no in (1, 2, 3):
                    self.assertTrue(process_scheduled_step())
                    run.refresh_from_db()
                    self.assertEqual(run.retry_round, round_no)
            self.assertEqual(calls, ['100002'] * 4)
            self.assertFalse(process_scheduled_step())
            self.assertEqual(run.attempts.get(eiin='100002').attempts, 4)
            self.assertIn('100002', (Path(directory) / str(run.pk) / 'failed.txt').read_text(encoding='utf-8'))

    def test_old_completed_months_are_removed_but_recent_logs_remain(self):
        with TemporaryDirectory() as directory, override_settings(INSTITUTE_UPDATE_LOG_ROOT=directory):
            old = InstituteUpdateRun.objects.create(status='complete', retry_round=3)
            recent = InstituteUpdateRun.objects.create(status='complete', retry_round=3)
            InstituteUpdateRun.objects.filter(pk=old.pk).update(
                started_at=datetime(2026, 7, 31, tzinfo=datetime_timezone.utc))
            InstituteUpdateRun.objects.filter(pk=recent.pk).update(
                started_at=datetime(2026, 8, 1, tzinfo=datetime_timezone.utc))
            old_path = Path(directory) / str(old.pk)
            recent_path = Path(directory) / str(recent.pk)
            old_path.mkdir()
            recent_path.mkdir()
            (old_path / 'failed.txt').write_text('old', encoding='utf-8')
            (recent_path / 'completed.txt').write_text('new', encoding='utf-8')
            old_event = InstituteRefreshEvent.objects.create(eiin='100002', status='failed')
            recent_event = InstituteRefreshEvent.objects.create(eiin='100002', status='complete')
            InstituteRefreshEvent.objects.filter(pk=old_event.pk).update(
                checked_at=datetime(2026, 7, 31, tzinfo=datetime_timezone.utc))
            InstituteRefreshEvent.objects.filter(pk=recent_event.pk).update(
                checked_at=datetime(2026, 8, 1, tzinfo=datetime_timezone.utc))
            self.assertEqual(prune_old_update_records(date(2026, 10, 14)), 1)
            self.assertFalse(old_path.exists())
            self.assertTrue(recent_path.exists())
            self.assertFalse(InstituteUpdateRun.objects.filter(pk=old.pk).exists())
            self.assertFalse(InstituteRefreshEvent.objects.filter(pk=old_event.pk).exists())
            self.assertTrue(InstituteRefreshEvent.objects.filter(pk=recent_event.pk).exists())
