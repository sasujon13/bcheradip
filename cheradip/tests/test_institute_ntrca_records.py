from contextlib import ExitStack
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from cheradip.institute_scraper_views import InstituteNtrcaRecordsView


class InstituteNtrcaRecordsTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = InstituteNtrcaRecordsView.as_view()

    def test_rejects_invalid_eiin(self):
        response = self.view(self.factory.get('/api/institutes/x/ntrca-records/'), eiin='x')
        self.assertEqual(response.status_code, 400)

    def test_returns_all_matching_rounds_without_other_institutes(self):
        models = ('Vacancy5', 'Vacancy6', 'Vacancy7', 'Recommend5', 'Recommend6', 'Recommend7')
        with ExitStack() as stack:
            mocks = {
                name: stack.enter_context(patch(f'cheradip.institute_scraper_views.{name}'))
                for name in models
            }
            for name, model in mocks.items():
                model.objects.filter.return_value.order_by.return_value.values.return_value = (
                    [{'VPID': 42, 'Vacancy': 2}] if name == 'Vacancy6' else
                    [{'id': 7, 'Name': 'Candidate'}] if name == 'Recommend7' else []
                )
            response = self.view(
                self.factory.get('/api/institutes/100005/ntrca-records/'), eiin='100005'
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['vacancies'], [{'cycle': 6, 'VPID': 42, 'Vacancy': 2}])
        self.assertEqual(response.data['recommendations'], [{'cycle': 7, 'id': 7, 'Name': 'Candidate'}])
        for model in mocks.values():
            model.objects.filter.assert_called_once_with(EIIN=100005)
