from django.test import SimpleTestCase

from cheradip.views import (
    _canonicalize_roman_triplet_markers,
    _export_wrap_mcq_line_html,
)


class RomanExportLayoutTests(SimpleTestCase):
    def test_canonicalizes_complete_roman_triplets_without_periods(self):
        self.assertEqual(
            _canonicalize_roman_triplet_markers('I first II second III third'),
            'I. first II. second III. third',
        )

    def test_c_expression_triplet_exports_as_three_separate_lines(self):
        source = (
            '-এর সমতুল্য সি এক্সপ্রেশন— '
            'i. Y=(pow(p,2))*x+2/3'
            'ii. Y=(pow(2,p))*x+2/3'
            'iii. Y=p*p*x+2/3'
        )

        rendered = _export_wrap_mcq_line_html(source, 'http://localhost', 1000, 16)

        self.assertEqual(rendered.count('roman-mcq-pack-line'), 3)
        self.assertIn('i. Y=', rendered)
        self.assertIn('ii. Y=', rendered)
        self.assertIn('iii. Y=', rendered)
