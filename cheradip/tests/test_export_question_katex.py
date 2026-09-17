from unittest import skipUnless

from django.test import SimpleTestCase

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False

from cheradip.export_question_katex import (
    EXPORT_KATEX_PDF_CSS,
    inject_katex_into_playwright_page,
    iter_question_latex_segments,
    katex_static_assets_available,
    latex_to_readable_text,
    normalize_question_calculation_layout,
    normalize_question_latex_source,
)


class QuestionLatexRepairTests(SimpleTestCase):
    def test_repeated_calculation_label_becomes_continuation_lines(self):
        source = (
            'ব্যাখ্যা শেষ।প্রকৃত তাপমাত্রা = 0°C+(51°C−4°C)×100/94'
            'প্রকৃত তাপমাত্রা = 47×100/94°C'
            'প্রকৃত তাপমাত্রা = 50°Cসুতরাং, প্রকৃত পাঠ 50°C।'
        )

        normalized = normalize_question_calculation_layout(source)

        self.assertEqual(
            normalized,
            'ব্যাখ্যা শেষ।\nপ্রকৃত তাপমাত্রা = 0°C+(51°C−4°C)×100/94\n'
            '= 47×100/94°C\n= 50°C\nসুতরাং, প্রকৃত পাঠ 50°C।',
        )
        self.assertEqual(normalized.count('প্রকৃত তাপমাত্রা ='), 1)

    def test_bengali_danda_spacing_does_not_change_protected_math(self):
        self.assertEqual(
            normalize_question_calculation_layout('প্রথম।দ্বিতীয় $$\\text{এক।দুই}$$'),
            'প্রথম। দ্বিতীয় $$\\text{এক।দুই}$$',
        )

    def test_escaped_multiplication_is_repaired_in_adjacent_display_math(self):
        source = normalize_question_latex_source(
            r'x=10$$y=x \* 5$$y=y \\% 3উদ্দীপকে উল্লিখিত y চলকের সর্বশেষ মান কত?'
        )

        self.assertIn(r'$$y=x \times', source)
        self.assertNotIn(r'\*', source)
        self.assertIn(r'$$y=y \% 3$$', source)
        self.assertEqual(normalize_question_latex_source(source), source)

    def test_wraps_bare_fraction_and_closes_aligned_display(self):
        source = (
            'ঘনমাত্রা, S=\\frac{W}{M V}$$\\begin{aligned}\\therefore W &=S '
            '\\times M \\times V \\\\ &=2.65 \\mathrm{\\~g}\\end{aligned}যেখানে'
        )
        normalized = normalize_question_latex_source(source)

        self.assertIn('$S=\\frac{W}{M V}$', normalized)
        self.assertNotIn('$$$', normalized)
        self.assertIn('$$\\begin{aligned}', normalized)
        self.assertIn('\\mathrm{g}\\end{aligned}$$যেখানে', normalized)

    def test_repairs_legacy_subscripts_and_orphan_display(self):
        source = (
            'অ্যাভোগাড্রোর সংখ্যা, \\mathrm{N}*{\\mathrm{A}}=6.02 \\times '
            '10^{23} \\text{molecule} \\mathrm{mol}^{-1}$$=1.38 \\times '
            '10^{-23} \\mathrm{Jk}^{-1}সুতরাং'
        )
        normalized = normalize_question_latex_source(source)

        self.assertIn('$\\mathrm{N}_{\\mathrm{A}}=6.02', normalized)
        self.assertNotIn('$$$', normalized)
        self.assertIn('$$=1.38 \\times 10^{-23} \\mathrm{Jk}^{-1}$$সুতরাং', normalized)

    def test_repairs_mixed_single_and_double_dollar_formula(self):
        source = (
            'সংকেত-$\\text{i. } \\mathrm{PbCrO}*{4}$$\\text{ ii. } '
            '\\mathrm{Na}*{2} \\mathrm{CO}*{3}$$\\text{iii. } '
            '\\mathrm{K}*{2} \\mathrm{CO}_{3}$নিচের'
        )
        normalized = normalize_question_latex_source(source)

        self.assertIn('$$\\text{i.} \\mathrm{PbCrO}_{4}\\\\\\text{ii.}', normalized)
        self.assertIn('\\mathrm{Na}_{2} \\mathrm{CO}_{3}', normalized)
        self.assertIn('\\mathrm{K}_{2} \\mathrm{CO}_{3}$$নিচের', normalized)

    def test_docx_segments_and_fallback_do_not_expose_tex_commands(self):
        source = 'মান, S=\\frac{W}{M V} এবং $x \\times y$।'
        segments = list(iter_question_latex_segments(source))
        formulas = [value for kind, value, _display in segments if kind == 'math']

        self.assertEqual(formulas, ['S=\\frac{W}{M V}', 'x \\times y'])
        fallback = latex_to_readable_text(formulas[0])
        self.assertEqual(fallback, 'S=(W)/(M V)')
        self.assertNotIn('\\frac', fallback)

    def test_bare_math_stops_before_following_english_prose(self):
        normalized = normalize_question_latex_source('Use x=\\frac{W}{M} where x is the result.')
        self.assertEqual(normalized, 'Use $x=\\frac{W}{M}$ where x is the result.')

    def test_repairs_single_open_double_close_list_with_stray_dollar(self):
        source = (
            'রুদ্ধতাপীয় পরিবর্তনের ক্ষেত্রে- $i. PV^{\\gamma}=k '
            'ii. Tv^{\\gamma-1}=k iii. T^{$\\gamma}P^{1+\\gamma}=k$$'
            'নিচের কোনটি সঠিক?'
        )
        normalized = normalize_question_latex_source(source)

        self.assertIn('$$\\text{i.} PV^{\\gamma}=k', normalized)
        self.assertIn('\\quad \\text{ii.} Tv^{\\gamma-1}=k', normalized)
        self.assertIn('T^{\\gamma}P^{1+\\gamma}=k$$নিচের', normalized)
        self.assertNotIn('T^{$', normalized)
        self.assertNotIn('$$$', normalized)

    @skipUnless(
        PLAYWRIGHT_AVAILABLE and katex_static_assets_available(),
        'PDF KaTeX rendering requires Playwright and the bundled assets',
    )
    def test_pdf_injection_renders_repaired_math_after_set_content(self):
        source = normalize_question_latex_source(
            'সূত্র- $i. PV^{\\gamma}=k iii. T^{$\\gamma}P^{1+\\gamma}=k$$পরে'
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content('<!doctype html><div id="formula">%s</div>' % source)
                inject_katex_into_playwright_page(page)
                page.wait_for_function('window.__katexPdfDone === true')
                rendered = page.locator('#formula').inner_html()
            finally:
                browser.close()

        self.assertIn('class="katex-display"', rendered)
        self.assertNotIn('T^{$', rendered)

    @skipUnless(
        PLAYWRIGHT_AVAILABLE and katex_static_assets_available(),
        'PDF KaTeX rendering requires Playwright and the bundled assets',
    )
    def test_pdf_display_result_is_a_left_aligned_block_without_delimiters(self):
        source = normalize_question_latex_source(
            'মান বসিয়ে পাই:W = 300 J / 2.5'
            '$$W = 120 J$$'
            'সুতরাং, প্রয়োজনীয় কাজ 120 J।'
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(
                    '<!doctype html><style>%s</style><div id="explanation">%s</div>'
                    % (EXPORT_KATEX_PDF_CSS, source)
                )
                inject_katex_into_playwright_page(page)
                page.wait_for_function('window.__katexPdfDone === true')
                rendered = page.locator('#explanation').inner_html()
                display_style = page.locator('#explanation .katex-display').evaluate(
                    "element => ({ display: getComputedStyle(element).display, "
                    "textAlign: getComputedStyle(element).textAlign, "
                    "innerTextAlign: getComputedStyle(element.querySelector('.katex')).textAlign })"
                )
            finally:
                browser.close()

        self.assertIn('class="katex-display"', rendered)
        self.assertNotIn('$$', rendered)
        self.assertEqual(
            display_style,
            {'display': 'block', 'textAlign': 'left', 'innerTextAlign': 'left'},
        )

    @skipUnless(
        PLAYWRIGHT_AVAILABLE and katex_static_assets_available(),
        'PDF KaTeX rendering requires Playwright and the bundled assets',
    )
    def test_pdf_failed_display_conversion_keeps_plain_formula_on_separate_line(self):
        source = 'আগে$$\\notacommand{W = 120 J}$$পরে'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(
                    '<!doctype html><style>%s</style><div id="explanation">%s</div>'
                    % (EXPORT_KATEX_PDF_CSS, source)
                )
                inject_katex_into_playwright_page(page)
                page.wait_for_function('window.__katexPdfDone === true')
                rendered = page.locator('#explanation').inner_html()
                fallback = page.locator('#explanation .question-math-fallback-display')
                fallback_style = fallback.evaluate(
                    "element => ({ display: getComputedStyle(element).display, "
                    "textAlign: getComputedStyle(element).textAlign })"
                )
                fallback_text = fallback.inner_text()
            finally:
                browser.close()

        self.assertNotIn('$$', rendered)
        self.assertEqual(fallback_text, r'\notacommand{W = 120 J}')
        self.assertEqual(fallback_style, {'display': 'block', 'textAlign': 'left'})
