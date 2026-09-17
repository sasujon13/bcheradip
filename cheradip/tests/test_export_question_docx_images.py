import base64
import tempfile
from unittest import skipUnless
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from django.test import SimpleTestCase, override_settings
from PIL import Image

from cheradip.views import ExportQuestionsView, PLAYWRIGHT_AVAILABLE


def png_bytes(color):
    output = BytesIO()
    Image.new('RGB', (80, 40), color).save(output, format='PNG')
    return output.getvalue()


class QuestionDocxImageExportTests(SimpleTestCase):
    def test_embeds_media_paths_and_html_images_instead_of_printing_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            local_png = png_bytes((220, 30, 30))
            (media_root / 'sample.png').write_bytes(local_png)
            data_png = png_bytes((30, 80, 220))
            data_uri = 'data:image/png;base64,' + base64.b64encode(data_png).decode('ascii')
            questions = [
                {
                    'qid': 'image-question',
                    'type': 'বহুনির্বাচনি প্রশ্ন',
                    'question': 'চিত্রটি দেখুন /media/sample.png',
                    'option_1': '<img src="%s" alt="option image" />' % data_uri,
                    'option_2': 'দ্বিতীয় উত্তর',
                },
                {
                    'qid': 'image-answer',
                    'type': 'বহুনির্বাচনি প্রশ্ন',
                    'answerSheetSegmentKind': 'tail',
                    'answerSheetTailKind': 'answer',
                    'answerSheetAnswerLabel': 'উত্তর',
                    'answerSheetAnswerText': '/media/sample.png',
                },
                {
                    'qid': 'image-explanation',
                    'type': 'বহুনির্বাচনি প্রশ্ন',
                    'answerSheetSegmentKind': 'tail',
                    'answerSheetTailKind': 'explanation',
                    'answerSheetExplanationLabel': 'ব্যাখ্যা',
                    'answerSheetExplanationText': '<img src="%s" />' % data_uri,
                },
            ]

            with override_settings(MEDIA_ROOT=temp_dir, HOST_URL='http://127.0.0.1:8000'):
                exported = ExportQuestionsView()._build_docx(
                    questions,
                    '',
                    18,
                    18,
                    18,
                    18,
                    210,
                    297,
                    raw_data={'pageSize': 'A4'},
                )

            with ZipFile(exported) as package:
                media = [name for name in package.namelist() if name.startswith('word/media/')]
                document_xml = package.read('word/document.xml').decode('utf-8')

            self.assertGreaterEqual(len(media), 2)
            self.assertGreaterEqual(document_xml.count('<a:blip '), 4)
            self.assertNotIn('/media/sample.png', document_xml)
            self.assertNotIn('data:image/', document_xml)
            self.assertNotIn('[Image unavailable]', document_xml)

    @skipUnless(PLAYWRIGHT_AVAILABLE, 'SVG rasterization requires Playwright')
    def test_embeds_compiled_svg_when_the_referenced_raster_is_absent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            (media_root / 'latex').mkdir()
            (media_root / 'latex' / 'formula.svg').write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="60">'
                '<rect width="160" height="60" fill="white"/>'
                '<text x="10" y="38" font-size="24">x² + y²</text></svg>',
                encoding='utf-8',
            )
            questions = [{
                'qid': 'svg-image-question',
                'type': 'বহুনির্বাচনি প্রশ্ন',
                'question': 'সূত্র /media/formula.png',
                'option_1': 'এক',
                'option_2': 'দুই',
            }]

            with override_settings(MEDIA_ROOT=temp_dir, HOST_URL='http://127.0.0.1:8000'):
                exported = ExportQuestionsView()._build_docx(
                    questions, '', 18, 18, 18, 18, 210, 297,
                    raw_data={'pageSize': 'A4'},
                )

            with ZipFile(exported) as package:
                media = [name for name in package.namelist() if name.startswith('word/media/')]
                document_xml = package.read('word/document.xml').decode('utf-8')

            self.assertEqual(len(media), 1)
            self.assertTrue(media[0].endswith('.png'))
            self.assertIn('<a:blip ', document_xml)
            self.assertNotIn('[Image unavailable]', document_xml)
