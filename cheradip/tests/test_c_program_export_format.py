from django.test import SimpleTestCase

from cheradip.c_program_export_format import format_maybe_c_program_question_text


class CProgramExportFormattingTests(SimpleTestCase):
    def test_brace_wrapped_dense_snippet_between_bengali_prose_is_code(self):
        source = (
            'নিচের উদ্দীপকটি পড় এবং ২১৯ ও ২২০নং প্রশ্নের উত্তর দাও:'
            '{int a = 2; b; b = ++a; Printf("%d",b);}'
            "উদ্দীপকে 'b' এর মান কত?"
        )

        formatted = format_maybe_c_program_question_text(source)

        self.assertIn('<span class="q-code-block"><code>', formatted)
        self.assertIn('int a = 2;<br />', formatted)
        self.assertIn('b = ++a;<br />', formatted)
        self.assertIn('Printf(&quot;%d&quot;,b);', formatted)
        self.assertIn("উদ্দীপকে 'b' এর মান কত?", formatted)

        plain = format_maybe_c_program_question_text(source, emit_html=False)
        self.assertNotIn('q-code-block', plain)
        self.assertIn('\n    int a = 2;\n', plain)
        self.assertIn('\n    Printf("%d",b);\n', plain)
