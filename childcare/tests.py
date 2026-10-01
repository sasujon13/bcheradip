from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from childcare.db_routers import ChildcareRouter


@override_settings(SECURE_SSL_REDIRECT=False)
class ChildcareSmokeTests(SimpleTestCase):
    def test_health_endpoint(self):
        response = self.client.get(reverse("cc-health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "childcare")

    def test_me_requires_session(self):
        response = self.client.get(reverse("cc-me"))
        self.assertEqual(response.status_code, 401)


class ChildcareDatabaseRouterTests(SimpleTestCase):
    def setUp(self):
        self.router = ChildcareRouter()

    def test_childcare_models_use_separate_database(self):
        class Meta:
            app_label = "childcare"

        class Model:
            _meta = Meta()

        self.assertEqual(self.router.db_for_read(Model), "childcare")
        self.assertEqual(self.router.db_for_write(Model), "childcare")

    def test_childcare_migrations_are_isolated(self):
        self.assertTrue(self.router.allow_migrate("childcare", "childcare"))
        self.assertFalse(self.router.allow_migrate("default", "childcare"))
