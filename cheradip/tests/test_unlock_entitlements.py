from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from cheradip.question_access import bind_legacy, package_covers, question_key
from cheradip.models import Banbeis
from cheradip.serializers import BanbeisSerializer
from cheradip.unlock_entitlements import (
    INSTITUTE_EXPIRIES, INSTITUTE_KEYS, PACKAGE_INSTITUTES, QUESTION_EXPIRIES, QUESTION_KEYS,
    active_coin_unlocks, effective_institute_eiins, grant_coin_unlock,
)
from cheradip.institute_scraper import _parse_emis_date, fetch_emis_teachers
from cheradip.institute_scraper_views import _staff_sort_key


class TimedCoinUnlockTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, tzinfo=datetime_timezone.utc)

    def test_new_question_and_institute_unlocks_last_two_calendar_years(self):
        data = {}
        grant_coin_unlock(data, QUESTION_KEYS, QUESTION_EXPIRIES, 'question-1', self.now)
        grant_coin_unlock(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES, '114770', self.now)
        before_expiry = self.now.replace(year=2028) - timedelta(seconds=1)
        at_expiry = self.now.replace(year=2028)
        self.assertEqual(active_coin_unlocks(data, QUESTION_KEYS, QUESTION_EXPIRIES, before_expiry), {'question-1'})
        self.assertEqual(active_coin_unlocks(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES, before_expiry), {'114770'})
        self.assertEqual(active_coin_unlocks(data, QUESTION_KEYS, QUESTION_EXPIRIES, at_expiry), set())
        self.assertEqual(active_coin_unlocks(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES, at_expiry), set())

    def test_undated_legacy_unlock_gets_one_migration_term(self):
        data = {INSTITUTE_KEYS: ['114770']}
        self.assertEqual(active_coin_unlocks(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES, self.now), {'114770'})
        first_deadline = data[INSTITUTE_EXPIRIES]['114770']
        self.assertEqual(active_coin_unlocks(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES, self.now + timedelta(days=1)), {'114770'})
        self.assertEqual(data[INSTITUTE_EXPIRIES]['114770'], first_deadline)
        self.assertEqual(active_coin_unlocks(data, INSTITUTE_KEYS, INSTITUTE_EXPIRIES, self.now.replace(year=2028)), set())

    def test_any_paid_plan_covers_question_unlock_but_teacher_free_does_not(self):
        question = {'subsource': "DU'25"}
        teacher_paid = SimpleNamespace(plan=SimpleNamespace(price=150, audience='teacher', track='academic'))
        teacher_free = SimpleNamespace(plan=SimpleNamespace(price=0, audience='teacher', track='academic'))
        self.assertTrue(package_covers([teacher_paid], question))
        self.assertFalse(package_covers([teacher_free], question))

    def test_expired_legacy_question_claim_is_not_regranted(self):
        data = {'unlocked_question_qids': ['1']}
        key = question_key('hsc', 'physics', '1')
        self.assertIn(key, bind_legacy(data, 'hsc', 'physics', [{'qid': '1'}]))
        data[QUESTION_EXPIRIES][key] = (self.now - timedelta(seconds=1)).isoformat()
        self.assertNotIn(key, bind_legacy(data, 'hsc', 'physics', [{'qid': '1'}]))

    def test_subscription_institute_unlock_disappears_when_plan_ends(self):
        customer = SimpleNamespace(pk=1, is_authenticated=True)
        data = {PACKAGE_INSTITUTES: ['114770']}
        with patch('cheradip.unlock_entitlements.migrate_unlock_settings', return_value=data), \
             patch('cheradip.unlock_entitlements.has_active_paid_package', return_value=True):
            self.assertEqual(effective_institute_eiins(customer), {'114770'})
        with patch('cheradip.unlock_entitlements.migrate_unlock_settings', return_value=data), \
             patch('cheradip.unlock_entitlements.has_active_paid_package', return_value=False):
            self.assertEqual(effective_institute_eiins(customer), set())

    def test_detail_serializer_marks_locked_and_unlocked_records(self):
        row = Banbeis(EIIN=114770, EducationLevels='Secondary', Contact='01700000000', Record='[[1,2,3]]')
        guest = SimpleNamespace(user=SimpleNamespace(is_authenticated=False, is_staff=False))
        locked = BanbeisSerializer(row, context={'request': guest}).data
        self.assertFalse(locked['detailsUnlocked'])
        self.assertEqual(locked['EducationLevels'], 'Secondary')
        self.assertIsNone(locked['Contact'])
        staff = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, is_staff=True))
        unlocked = BanbeisSerializer(row, context={'request': staff}).data
        self.assertTrue(unlocked['detailsUnlocked'])
        self.assertEqual(unlocked['Contact'], '01700000000')

    def test_public_institute_page_exposes_details_without_opening_other_endpoints(self):
        from cheradip.institute_scraper_views import PublicInstitutePageDetailsView

        row = Banbeis(EIIN=100001, Contact='01700000000', Record='[[1,2,3]]')
        guest = SimpleNamespace(user=SimpleNamespace(is_authenticated=False, is_staff=False))
        self.assertIsNone(BanbeisSerializer(row, context={'request': guest}).data['Contact'])
        teacher = SimpleNamespace(name='Teacher', name_bn='', designation='Teacher',
                                  subject='Science', mobile='01800000000', email='teacher@example.com',
                                  pds_id='', index_no='', district_name='', bcs_batch='',
                                  photo_url='', joining_date=None, present_joining_date=None, position=0)
        teacher_query = MagicMock()
        teacher_query.order_by.return_value.__getitem__.return_value = [teacher]
        with patch('cheradip.institute_scraper_views.Banbeis.objects.filter') as banbeis_filter, \
             patch('cheradip.institute_scraper_views.InstituteSourceSnapshot.objects.filter') as snapshot_filter, \
             patch('cheradip.institute_scraper_views.InstituteTeacher.objects.filter', return_value=teacher_query):
            banbeis_filter.return_value.first.return_value = row
            snapshot_filter.return_value.first.return_value = SimpleNamespace(
                banbeis={'managementNameBn': 'বেসরকারি', 'webSite': 'example.edu.bd',
                         'campusFacilityCount': 4, 'esurveyId': 77,
                         'internalSecretStatus': 'private', 'id': 123},
                last_banbeis_sync_at=None, last_emis_sync_at=None,
            )
            request = APIRequestFactory().get('/api/institutes/100001/page-details/')
            response = PublicInstitutePageDetailsView.as_view()(request, eiin='100001')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['banbeis']['Contact'], '01700000000')
        self.assertEqual(response.data['teachers'][0]['mobile'], '01800000000')
        self.assertEqual(response.data['sourceDetails']['managementNameBn'], 'বেসরকারি')
        self.assertNotIn('id', response.data['sourceDetails'])
        self.assertEqual(response.data['additionalDetails'], [{'label': 'Campus Facility Count', 'value': '4'}])

    def test_emis_staff_import_includes_support_staff_and_joining_date(self):
        response = MagicMock()
        response.json.return_value = [{
            'Id': 7, 'FullName': 'Office Assistant',
            'InstituteInstituteNameInBangla': 'বিদ্যালয়',
            'DesignationNameBn': 'অফিস সহকারী', 'JoiningDate': "'03-Jun-2010'",
            'PresentJoiningDate': '2011-07-04', 'EmpId': 'PDS-1', 'IndexNo': 'IDX-1',
            'Image': "<img src='/EMIS/upload/HRM/EmpCollRegisImage/1/teacher.jpg'>",
        }]
        session = MagicMock()
        session.post.return_value = response
        directory = {'Id': 3, 'Eiin': '100001', 'InstituteNameInBangla': 'বিদ্যালয়'}
        rows = fetch_emis_teachers(session, '100001', directory)
        self.assertEqual(session.post.call_args.kwargs['data']['isTeacher'], 0)
        self.assertEqual(rows[0]['joining_date'], _parse_emis_date('03-Jun-2010'))
        self.assertEqual(rows[0]['pds_id'], 'PDS-1')
        self.assertEqual(rows[0]['photo_url'], 'https://emis.gov.bd/EMIS/upload/HRM/EmpCollRegisImage/1/teacher.jpg')
        from cheradip.institute_scraper import _emis_photo_url
        self.assertEqual(_emis_photo_url("<img src='/EMIS/upload/HRM/UserImage/1/staff.png'>"),
                         'https://emis.gov.bd/EMIS/upload/HRM/UserImage/1/staff.png')

    def test_staff_sorts_designation_before_oldest_joining_date(self):
        from datetime import date
        rows = [
            SimpleNamespace(designation='সহকারী শিক্ষক', joining_date=date(2020, 1, 1), present_joining_date=None, name='B', name_bn='', position=0),
            SimpleNamespace(designation='প্রধান শিক্ষক', joining_date=None, present_joining_date=None, name='Head', name_bn='', position=0),
            SimpleNamespace(designation='সহকারী শিক্ষক', joining_date=date(2010, 1, 1), present_joining_date=None, name='A', name_bn='', position=1),
        ]
        self.assertEqual([row.name for row in sorted(rows, key=_staff_sort_key)], ['Head', 'A', 'B'])
