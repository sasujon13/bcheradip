from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from cheradip.management.commands.ensure_package_catalog import expected_plans
from cheradip.models import PackagePlan


class EnsurePackageCatalogTests(TestCase):
    def test_canonical_catalog_matches_student_and_teacher_matrix(self):
        expected = dict(expected_plans())
        self.assertEqual(len(expected), 48)
        self.assertEqual(expected['free-academic']['duration_months'], 1)
        self.assertEqual(expected['teacher-free-academic']['duration_months'], 36)
        self.assertEqual(expected['teacher-advanced-3-combined']['question_limit'], 1080)

    def test_adds_only_missing_plans_and_is_idempotent(self):
        call_command('ensure_package_catalog', '--apply-missing', stdout=StringIO())
        self.assertEqual(PackagePlan.objects.count(), 48)
        call_command('ensure_package_catalog', '--apply-missing', stdout=StringIO())
        self.assertEqual(PackagePlan.objects.count(), 48)

    def test_conflicting_existing_plan_is_not_overwritten(self):
        defaults = dict(expected_plans())['starter-academic']
        PackagePlan.objects.create(code='starter-academic', **{**defaults, 'price': 999})
        with self.assertRaises(CommandError):
            call_command('ensure_package_catalog', '--apply-missing',
                         stdout=StringIO(), stderr=StringIO())
        self.assertEqual(PackagePlan.objects.count(), 1)
        self.assertEqual(PackagePlan.objects.get(code='starter-academic').price, 999)
