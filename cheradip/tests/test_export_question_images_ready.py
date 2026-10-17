import base64
from io import BytesIO
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from PIL import Image

from cheradip.views import (
    ExportQuestionImageError,
    ExportQuestionsView,
    PLAYWRIGHT_AVAILABLE,
    _EXPORT_Q_RICH_IMG_PDF_SCRIPT,
    _playwright_wait_for_export_rich_images,
)


class ExportQuestionImageReadinessTests(SimpleTestCase):
    def test_pdf_wait_rejects_failed_images(self):
        page = Mock()
        page.evaluate.return_value = 2

        with self.assertRaisesRegex(ExportQuestionImageError, '2 question image'):
            _playwright_wait_for_export_rich_images(page)

        page.pdf.assert_not_called()

    def test_pdf_wait_rejects_timeout_instead_of_exporting_incomplete_page(self):
        page = Mock()
        page.wait_for_function.side_effect = TimeoutError('image timeout')

        with self.assertRaisesRegex(ExportQuestionImageError, 'did not finish loading'):
            _playwright_wait_for_export_rich_images(page)

        page.evaluate.assert_not_called()

    def test_pdf_wait_accepts_loaded_images(self):
        page = Mock()
        page.evaluate.return_value = 0

        _playwright_wait_for_export_rich_images(page)

        page.wait_for_timeout.assert_called_once_with(120)

    def test_pdf_image_cap_matches_preview_without_extra_shrink(self):
        self.assertNotIn('EXPORT_PDF_RICH_IMG_SCALE', _EXPORT_Q_RICH_IMG_PDF_SCRIPT)
        self.assertIn('var cap=widthCap(img,maxCap)', _EXPORT_Q_RICH_IMG_PDF_SCRIPT)

    def test_docx_rejects_unavailable_image_instead_of_printing_placeholder(self):
        questions = [{
            'qid': 'missing-image',
            'type': 'বহুনির্বাচনি প্রশ্ন',
            'question': 'চিত্রটি দেখুন /media/definitely_missing_question_image.png',
            'option_1': 'এক',
            'option_2': 'দুই',
        }]

        with patch('cheradip.views._export_docx_load_image_bytes', return_value=None), self.assertRaisesRegex(
            ExportQuestionImageError, 'could not be embedded'
        ):
            ExportQuestionsView()._build_docx(
                questions, '', 18, 18, 18, 18, 210, 297,
                raw_data={'pageSize': 'A4'},
            )

    @skipUnless(PLAYWRIGHT_AVAILABLE, 'Playwright is not installed')
    def test_browser_sizes_loaded_image_to_column_and_rejects_broken_one(self):
        from playwright.sync_api import sync_playwright

        output = BytesIO()
        Image.new('RGB', (80, 40), (20, 130, 130)).save(output, format='PNG')
        source = 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page()
                    page.set_content(
                        '<div class="q-content" style="width:50px;font-size:20px">'
                        f'<img class="q-rich-img" src="{source}"></div>'
                        + _EXPORT_Q_RICH_IMG_PDF_SCRIPT,
                        wait_until='load',
                    )
                    _playwright_wait_for_export_rich_images(page)
                    width = page.locator('img').evaluate('(img) => img.getBoundingClientRect().width')
                    self.assertLessEqual(width, 50)
                    self.assertGreater(width, 0)

                    page.set_content(
                        '<img class="q-rich-img" src="data:image/png;base64,broken">'
                        + _EXPORT_Q_RICH_IMG_PDF_SCRIPT,
                        wait_until='load',
                    )
                    with self.assertRaises(ExportQuestionImageError):
                        _playwright_wait_for_export_rich_images(page)
                finally:
                    browser.close()
        except Exception as exc:
            if 'Executable doesn\'t exist' in str(exc):
                self.skipTest('Playwright Chromium is not installed')
            raise
