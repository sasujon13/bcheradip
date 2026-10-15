from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from cheradip.models import Banbeis, Customer, InstituteSourceSnapshot, InstituteTeacher, InstituteUpdateRun, Institutes
from cheradip.institute_scraper import InstituteSourceError, fetch_emis_teachers, sync_emis_teachers
from cheradip.serializers import InstitutesSerializer


@override_settings(SECURE_SSL_REDIRECT=False)
class InstituteScraperTests(TransactionTestCase):
    databases = {'default', 'job'}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connection = connections['job']
        cls.created_legacy_table = Institutes._meta.db_table not in connection.introspection.table_names()
        cls.created_banbeis_table = Banbeis._meta.db_table not in connection.introspection.table_names()
        if cls.created_legacy_table:
            with connection.schema_editor() as editor:
                editor.create_model(Institutes)
        if cls.created_banbeis_table:
            with connection.schema_editor() as editor:
                editor.create_model(Banbeis)

    @classmethod
    def tearDownClass(cls):
        if cls.created_banbeis_table:
            connection = connections['job']
            with connection.schema_editor() as editor:
                editor.delete_model(Banbeis)
        if cls.created_legacy_table:
            connection = connections['job']
            with connection.schema_editor() as editor:
                editor.delete_model(Institutes)
        super().tearDownClass()

    def setUp(self):
        Institutes.objects.all().delete()
        Banbeis.objects.all().delete()
        self.staff = Customer.objects.create_user(username='01718888888', password='pass', is_staff=True)
        self.customer = Customer.objects.create_user(username='01717777777', password='pass')
        self.client = APIClient()
        self.detail = {
            'id': 13292, 'eiinNo': '100001', 'instituteName': 'UMMUL QURA HIGH SCHOOL',
            'instituteNameBn': 'উম্মুল কুরা হাইস্কুল', 'mobile': '01558442605',
            'mobileAlternate': '01318927722', 'email': 'school@example.test',
            'divisionNameBn': 'বরিশাল', 'managementNameBn': 'বেসরকারি',
        }

    def test_access_requires_staff_and_preview_does_not_write(self):
        self.assertIn(self.client.get('/api/scraper/institutes/access/').status_code, (401, 403))
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get('/api/scraper/institutes/access/').status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/scraper/institutes/access/').status_code, 200)
        with patch('cheradip.institute_scraper.fetch_banbeis_page', return_value=([{'eiinNo': '100001'}], 40239)), \
             patch('cheradip.institute_scraper.fetch_banbeis_detail', return_value=self.detail), \
             patch('cheradip.institute_scraper.fetch_emis_directory_entry', return_value={}):
            response = self.client.post('/api/scraper/institutes/page/',
                                        {'page': 1, 'size': 10, 'mode': 'preview', 'enrichEmis': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['sourceTotal'], 40239)
        self.assertFalse(Institutes.objects.filter(eiinNo='100001').exists())

    def test_admin_session_requires_csrf_for_import(self):
        browser = APIClient(enforce_csrf_checks=True)
        browser.force_login(self.staff)
        self.assertEqual(browser.get('/api/scraper/institutes/access/').status_code, 200)
        payload = {'page': 1, 'size': 10, 'mode': 'preview', 'enrichEmis': False}
        self.assertEqual(browser.post('/api/scraper/institutes/page/', payload, format='json').status_code, 403)
        browser.cookies['csrftoken'] = 'a' * 32
        with patch('cheradip.institute_scraper.fetch_banbeis_page', return_value=([], 0)):
            allowed = browser.post('/api/scraper/institutes/page/', payload, format='json',
                                   HTTP_X_CSRFTOKEN='a' * 32)
        self.assertEqual(allowed.status_code, 200)

    def test_admin_session_can_use_legacy_question_scraper_with_csrf(self):
        browser = APIClient(enforce_csrf_checks=True)
        browser.force_login(self.staff)
        self.assertEqual(browser.get('/api/scraper/helper/').status_code, 200)
        self.assertEqual(browser.post('/api/run_scraper/', {}, format='json').status_code, 403)
        browser.cookies['csrftoken'] = 'a' * 32
        response = browser.post('/api/run_scraper/', {}, format='json', HTTP_X_CSRFTOKEN='a' * 32)
        self.assertEqual(response.status_code, 400)

    def test_apply_updates_by_eiin_and_keeps_public_contacts(self):
        self.client.force_authenticate(self.staff)
        url = '/api/scraper/institutes/page/'
        body = {'page': 1, 'size': 10, 'mode': 'apply', 'enrichEmis': True}
        emis = {'Id': 42236, 'Eiin': '100001', 'InstituteName': 'DIFFERENT NAME', 'InstituteNameInBangla': 'ভিন্ন নাম'}
        teachers = [{'source_row_id': '42', 'name': 'Teacher One', 'name_bn': 'শিক্ষক এক',
                     'designation': 'Assistant Teacher', 'subject': 'Physics', 'mobile': '01700000000',
                     'email': 'teacher@example.test', 'position': 0}]
        with patch('cheradip.institute_scraper.fetch_banbeis_page', return_value=([{'eiinNo': '100001'}], 40239)), \
             patch('cheradip.institute_scraper.fetch_banbeis_detail', return_value=self.detail), \
             patch('cheradip.institute_scraper.fetch_emis_directory_entry', return_value=emis), \
             patch('cheradip.institute_scraper.fetch_emis_teachers', return_value=teachers), \
             patch('cheradip.institute_scraper.time.sleep'):
            created = self.client.post(url, body, format='json')
            unchanged = self.client.post(url, body, format='json')
        self.assertEqual((created.status_code, created.data['created']), (200, 1))
        self.assertEqual(unchanged.data['unchanged'], 1)
        self.assertEqual(Institutes.objects.filter(eiinNo='100001').count(), 1)
        institute = Institutes.objects.get(eiinNo='100001')
        self.assertEqual(institute.instituteName, 'UMMUL QURA HIGH SCHOOL')
        self.assertEqual(institute.email, 'school@example.test')
        self.assertEqual(InstitutesSerializer(institute).data['mobile'], '01558442605')
        self.assertEqual(InstituteSourceSnapshot.objects.get(eiin='100001').emis['InstituteName'], 'DIFFERENT NAME')
        self.assertEqual(created.data['teachersCreated'], 1)
        self.assertEqual(unchanged.data['teachersCreated'], 0)
        self.assertEqual(InstituteTeacher.objects.filter(eiin='100001', listed=True).count(), 1)
        self.client.force_authenticate(user=None)
        public = self.client.get('/api/institutes/', {'search': '100001'})
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.data['results'][0]['mobile'], '01558442605')
        self.assertEqual(public.data['results'][0]['mobileAlternate'], '01318927722')
        self.assertEqual(public.data['results'][0]['email'], 'school@example.test')
        directory = self.client.get('/api/institutes/100001/teachers/')
        self.assertEqual(directory.status_code, 200)
        self.assertEqual(directory.data['teachers'][0]['nameBn'], 'শিক্ষক এক')
        self.assertEqual(directory.data['teachers'][0]['mobile'], '')
        self.customer.settings = {'unlocked_ntrca_eiins_v2': ['100001']}
        self.customer.save(update_fields=['settings'])
        self.client.force_authenticate(self.customer)
        paid_directory = self.client.get('/api/institutes/100001/teachers/')
        self.assertEqual(paid_directory.data['teachers'][0]['mobile'], '01700000000')
        self.client.force_authenticate(self.staff)
        staff_directory = self.client.get('/api/institutes/100001/teachers/')
        self.assertEqual(staff_directory.data['teachers'][0]['mobile'], '01700000000')

    def test_empty_roster_preserves_previous_entries(self):
        teacher = {'source_row_id': '8', 'name': 'Teacher', 'name_bn': '', 'designation': '',
                   'subject': '', 'mobile': '', 'email': '', 'position': 0}
        self.assertEqual(sync_emis_teachers('100001', [teacher])['created'], 1)
        self.assertEqual(sync_emis_teachers('100001', [])['unlisted'], 0)
        self.assertTrue(InstituteTeacher.objects.get(eiin='100001').listed)
        self.assertEqual(sync_emis_teachers('100001', [dict(teacher, source_row_id='9')])['unlisted'], 1)
        self.assertFalse(InstituteTeacher.objects.get(eiin='100001', source_row_id='8').listed)

    def test_mismatched_emis_roster_is_rejected(self):
        from unittest.mock import Mock
        response = Mock()
        response.json.return_value = [{'Id': 1, 'FullName': 'Teacher',
                                       'InstituteInstituteNameInBangla': 'অন্য বিদ্যালয়'}]
        session = Mock()
        session.post.return_value = response
        directory = {'Id': 55, 'Eiin': '100001', 'InstituteNameInBangla': 'আসল বিদ্যালয়'}
        with self.assertRaises(InstituteSourceError):
            fetch_emis_teachers(session, '100001', directory)
        self.assertEqual(InstituteTeacher.objects.count(), 0)

    def test_primary_banbeis_address_refreshes_existing_legacy_record(self):
        from cheradip.institute_scraper import save_institute
        Banbeis.objects.create(EIIN=100001, Name='Older name', PostOffice='Old office', WardNo='1')
        detail = {**self.detail, 'postOfficeNameBn': 'নতুন ডাকঘর', 'postOfficeCode': '1234', 'wardNo': '2'}
        save_institute('100001', detail, {})
        record = Banbeis.objects.get(EIIN=100001)
        self.assertEqual((record.PostOffice, record.PostCode, record.WardNo), ('নতুন ডাকঘর', '1234', '2'))
        self.assertEqual(record.Name, 'Older name')

    def test_single_eiin_preview_does_not_fetch_page_or_checkpoint(self):
        self.client.force_authenticate(self.staff)
        with patch('cheradip.institute_scraper.fetch_banbeis_page') as page_fetch, \
             patch('cheradip.institute_scraper.fetch_banbeis_detail', return_value=self.detail):
            response = self.client.post('/api/scraper/institutes/page/',
                                        {'page': 1, 'size': 10, 'eiin': '100001',
                                         'mode': 'preview', 'enrichEmis': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['records'][0]['status'], 'preview')
        self.assertFalse(Institutes.objects.filter(eiinNo='100001').exists())
        page_fetch.assert_not_called()
        invalid = self.client.post('/api/scraper/institutes/page/',
                                   {'page': 1, 'size': 10, 'eiin': '123',
                                    'mode': 'preview', 'enrichEmis': False}, format='json')
        self.assertEqual(invalid.status_code, 400)

    def test_emis_failure_does_not_block_banbeis_update(self):
        self.client.force_authenticate(self.staff)
        with patch('cheradip.institute_scraper.fetch_banbeis_page', return_value=([{'eiinNo': '100001'}], 40239)), \
             patch('cheradip.institute_scraper.fetch_banbeis_detail', return_value=self.detail), \
             patch('cheradip.institute_scraper.fetch_emis_directory_entry', side_effect=ValueError('EMIS unavailable')), \
             patch('cheradip.institute_scraper.time.sleep'):
            result = self.client.post('/api/scraper/institutes/page/',
                                      {'page': 2, 'size': 10, 'mode': 'apply', 'enrichEmis': True}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual((result.data['created'], result.data['emisSkipped']), (1, 1))

    def test_automatic_database_order_logs_and_retry_failed_file(self):
        with TemporaryDirectory() as directory, override_settings(INSTITUTE_UPDATE_LOG_ROOT=directory):
            for eiin in ('100003', '100001', '100002'):
                Institutes.objects.create(eiinNo=eiin, instituteName=f'School {eiin}')
            Institutes.objects.create(eiinNo='000000', instituteName='Placeholder')
            self.client.force_authenticate(self.staff)
            start = self.client.post('/api/scraper/institutes/automatic/start/', {'mode': 'all'}, format='json')
            self.assertEqual(start.status_code, 200)
            self.assertEqual(start.data['run']['total'], 3)
            run_id = start.data['run']['runId']
            seen = []

            def source_result(**kwargs):
                eiin = kwargs['eiin']
                seen.append(eiin)
                if eiin == '100002':
                    return {'failed': 1, 'records': [{'eiin': eiin, 'status': 'failed',
                                                      'detail': 'Banbeis unavailable'}]}
                return {'failed': 0, 'records': [{'eiin': eiin, 'status': 'unchanged',
                                                  'emisWarning': 'EMIS unavailable' if eiin == '100003' else ''}]}

            with patch('cheradip.institute_update_runs.process_institute_page', side_effect=source_result):
                step = self.client.post('/api/scraper/institutes/automatic/step/',
                                        {'mode': 'all', 'runId': run_id}, format='json')
            self.assertEqual(step.status_code, 200)
            self.assertEqual(seen, ['100001', '100002', '100003'])
            self.assertFalse(step.data['hasMore'])
            self.assertEqual((step.data['run']['completed'], step.data['run']['failed']), (2, 1))
            run = InstituteUpdateRun.objects.get(pk=run_id)
            completed = (Path(directory) / str(run.pk) / 'completed.txt').read_text(encoding='utf-8')
            failed = (Path(directory) / str(run.pk) / 'failed.txt').read_text(encoding='utf-8')
            self.assertIn('100001\tunchanged', completed)
            self.assertIn('100003\tunchanged', completed)
            self.assertNotIn('100003', failed)  # An EMIS warning is not a failed EIIN.
            self.assertIn('100002\tBanbeis unavailable', failed)

            retry = self.client.post('/api/scraper/institutes/automatic/start/', {'mode': 'failed'}, format='json')
            self.assertEqual(retry.data['selected'], 1)
            with patch('cheradip.institute_update_runs.process_institute_page',
                       return_value={'failed': 0, 'records': [{'eiin': '100002', 'status': 'updated'}]}):
                retried = self.client.post('/api/scraper/institutes/automatic/step/',
                                           {'mode': 'failed', 'runId': run_id}, format='json')
            self.assertEqual(retried.status_code, 200)
            self.assertEqual((retried.data['run']['completed'], retried.data['run']['failed']), (3, 0))
            self.assertEqual(len((Path(directory) / str(run.pk) / 'failed.txt').read_text(encoding='utf-8').splitlines()), 1)
            self.assertIn('100002\tupdated', (Path(directory) / str(run.pk) / 'completed.txt').read_text(encoding='utf-8'))
            download = self.client.get('/api/scraper/institutes/automatic/logs/completed/')
            self.assertEqual(download.status_code, 200)
            self.assertIn(b'100002\tupdated', b''.join(download.streaming_content))

    def test_automatic_update_requires_staff(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get('/api/scraper/institutes/automatic/status/').status_code, 403)
        self.assertEqual(self.client.post('/api/scraper/institutes/automatic/start/',
                                          {'mode': 'all'}, format='json').status_code, 403)
        self.assertEqual(self.client.get('/api/scraper/institutes/automatic/logs/failed/').status_code, 403)

    def test_automatic_update_resumes_from_saved_database_cursor(self):
        with TemporaryDirectory() as directory, override_settings(INSTITUTE_UPDATE_LOG_ROOT=directory):
            for eiin in ('100001', '100002', '100003', '100004'):
                Institutes.objects.create(eiinNo=eiin, instituteName=eiin)
            self.client.force_authenticate(self.staff)
            start = self.client.post('/api/scraper/institutes/automatic/start/', {'mode': 'all'}, format='json')
            run_id = start.data['run']['runId']
            seen = []

            def source_result(**kwargs):
                seen.append(kwargs['eiin'])
                return {'failed': 0, 'records': [{'eiin': kwargs['eiin'], 'status': 'unchanged'}]}

            with patch('cheradip.institute_update_runs.process_institute_page', side_effect=source_result):
                first = self.client.post('/api/scraper/institutes/automatic/step/',
                                         {'mode': 'all', 'runId': run_id}, format='json')
                resumed = self.client.post('/api/scraper/institutes/automatic/start/',
                                           {'mode': 'all'}, format='json')
                second = self.client.post('/api/scraper/institutes/automatic/step/',
                                          {'mode': 'all', 'runId': run_id}, format='json')
            self.assertTrue(first.data['hasMore'])
            self.assertEqual(resumed.data['run']['runId'], run_id)
            self.assertEqual(seen, ['100001', '100002', '100003', '100004'])
            self.assertFalse(second.data['hasMore'])
            self.assertEqual(second.data['run']['status'], 'complete')
