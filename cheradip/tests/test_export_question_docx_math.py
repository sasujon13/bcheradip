from unittest import skipUnless
from unittest.mock import patch
from zipfile import ZipFile

from django.test import SimpleTestCase

from cheradip.views import ExportQuestionsView, MATH2DOCX_AVAILABLE, PLAYWRIGHT_AVAILABLE


MALFORMED_PHYSICS_QUESTION = (
    'রুদ্ধতাপীয় পরিবর্তনের ক্ষেত্রে- $i. PV^{\\gamma}=k '
    'ii. Tv^{\\gamma-1}=k iii. T^{$\\gamma}P^{1+\\gamma}=k$$'
    'নিচের কোনটি সঠিক?'
)


def build_docx(question_text):
    questions = [{
        'qid': 'physics-math',
        'type': 'বহুনির্বাচনি প্রশ্ন',
        'question': question_text,
        'option_1': 'প্রথম',
        'option_2': 'দ্বিতীয়',
    }]
    return ExportQuestionsView()._build_docx(
        questions, '', 18, 18, 18, 18, 210, 297,
        raw_data={'pageSize': 'A4'},
    )


class QuestionDocxMathExportTests(SimpleTestCase):
    def test_roman_triplet_is_three_lines_in_docx(self):
        exported = build_docx(
            '-এর সমতুল্য সি এক্সপ্রেশন— '
            'i. Y=(pow(p,2))*x+2/3'
            'ii. Y=(pow(2,p))*x+2/3'
            'iii. Y=p*p*x+2/3'
        )

        with ZipFile(exported) as package:
            document_xml = package.read('word/document.xml').decode('utf-8')

        self.assertGreaterEqual(document_xml.count('<w:br/>'), 3)
        self.assertIn('i. Y=', document_xml)
        self.assertIn('ii. Y=', document_xml)
        self.assertIn('iii. Y=', document_xml)

    def test_brace_wrapped_c_snippet_uses_code_lines_and_monospace_font_in_docx(self):
        exported = build_docx(
            'ভূমিকা:{int a = 2; b; b = ++a; Printf("%d",b);}'
            "উদ্দীপকে 'b' এর মান কত?"
        )

        with ZipFile(exported) as package:
            document_xml = package.read('word/document.xml').decode('utf-8')

        self.assertIn('w:ascii="Consolas"', document_xml)
        self.assertIn('int a = 2;', document_xml)
        self.assertIn('b = ++a;', document_xml)
        self.assertGreaterEqual(document_xml.count('<w:br/>'), 5)

    def test_repeated_calculation_steps_are_separate_docx_lines(self):
        questions = [{
            'qid': 'calculation-layout',
            'type': 'বহুনির্বাচনি প্রশ্ন',
            'answerSheetSegmentKind': 'tail',
            'answerSheetTailKind': 'explanation',
            'answerSheetExplanationLabel': 'ব্যাখ্যা',
            'answerSheetExplanationText': (
                'শেষ।প্রকৃত তাপমাত্রা = 1প্রকৃত তাপমাত্রা = 2'
                'প্রকৃত তাপমাত্রা = 3সুতরাং, উত্তর 3।'
            ),
        }]
        exported = ExportQuestionsView()._build_docx(
            questions, '', 18, 18, 18, 18, 210, 297,
            raw_data={'pageSize': 'A4'},
        )

        with ZipFile(exported) as package:
            document_xml = package.read('word/document.xml').decode('utf-8')

        self.assertEqual(document_xml.count('প্রকৃত তাপমাত্রা ='), 1)
        self.assertGreaterEqual(document_xml.count('<w:br/>'), 4)
        self.assertIn('= 2', document_xml)
        self.assertIn('= 3', document_xml)

    @skipUnless(MATH2DOCX_AVAILABLE, 'Editable OMML conversion requires math2docx')
    def test_prefers_editable_omml_for_repaired_legacy_formula(self):
        exported = build_docx(MALFORMED_PHYSICS_QUESTION)

        with ZipFile(exported) as package:
            document_xml = package.read('word/document.xml').decode('utf-8')
            formula_images = [
                name for name in package.namelist()
                if name.startswith('word/media/')
            ]

        self.assertIn('<m:oMath', document_xml)
        self.assertNotIn('T^{$', document_xml)
        self.assertNotIn('\\gamma', document_xml)
        self.assertNotIn('$$$', document_xml)
        self.assertEqual(formula_images, [])

    @skipUnless(PLAYWRIGHT_AVAILABLE, 'Formula PNG fallback requires Playwright')
    def test_uses_png_when_omml_conversion_is_unavailable(self):
        with patch('cheradip.views.MATH2DOCX_AVAILABLE', False):
            exported = build_docx('সূত্র $PV^{\\gamma}=k$')

        with ZipFile(exported) as package:
            document_xml = package.read('word/document.xml').decode('utf-8')
            formula_images = [
                name for name in package.namelist()
                if name.startswith('word/media/')
            ]

        self.assertNotIn('<m:oMath', document_xml)
        self.assertIn('<a:blip ', document_xml)
        self.assertGreaterEqual(len(formula_images), 1)

    def test_preserves_raw_formula_as_last_resort(self):
        with (
            patch('cheradip.views.MATH2DOCX_AVAILABLE', False),
            patch('cheradip.views.PLAYWRIGHT_AVAILABLE', False),
        ):
            exported = build_docx('সূত্র $PV^{\\gamma}=k$')

        with ZipFile(exported) as package:
            document_xml = package.read('word/document.xml').decode('utf-8')

        self.assertNotIn('<m:oMath', document_xml)
        self.assertNotIn('<a:blip ', document_xml)
        self.assertIn('PV^{\\gamma}=k', document_xml)
        self.assertNotIn('$PV^{\\gamma}=k$', document_xml)

    @skipUnless(MATH2DOCX_AVAILABLE, 'Editable OMML conversion requires math2docx')
    def test_display_formula_is_between_line_breaks_in_explanation(self):
        questions = [{
            'qid': 'physics-explanation',
            'type': 'বহুনির্বাচনি প্রশ্ন',
            'answerSheetSegmentKind': 'tail',
            'answerSheetTailKind': 'explanation',
            'answerSheetExplanationLabel': 'ব্যাখ্যা',
            'answerSheetExplanationText': (
                'মান বসিয়ে পাই:W = 300 J / 2.5'
                '$$W = 120 J$$'
                'সুতরাং, প্রয়োজনীয় কাজ 120 J।'
            ),
        }]
        exported = ExportQuestionsView()._build_docx(
            questions, '', 18, 18, 18, 18, 210, 297,
            raw_data={'pageSize': 'A4'},
        )

        with ZipFile(exported) as package:
            document_xml = package.read('word/document.xml').decode('utf-8')

        self.assertIn('<m:oMath', document_xml)
        self.assertGreaterEqual(document_xml.count('<w:br/>'), 2)
        self.assertNotIn('$$W = 120 J$$', document_xml)
        self.assertRegex(
            document_xml,
            r'<w:r><w:br/></w:r><m:oMath[\s\S]+?</m:oMath><w:r><w:br/></w:r>',
        )
