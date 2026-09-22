"""Junk/garbage-character detection tests.

Covers ``cheradip.text_hygiene`` (the whitelist-aware scanner, the safe cleanup and the
formula guard) and its wiring into ``cheradip.question_updater`` (AI prompt + post-check).
"""
from unittest import mock

from django.test import SimpleTestCase

from cheradip.text_hygiene import (
    KIND_BROKEN,
    KIND_DANGLING,
    KIND_DOUBLE_SIGN,
    KIND_EMOJI,
    KIND_FOREIGN,
    KIND_INVISIBLE,
    KIND_LOOKALIKE,
    KIND_MATH_JUNK,
    KIND_MATH_UNBALANCED,
    KIND_SPACE,
    SCAN_FIELDS,
    build_prompt_block,
    candidate_lines,
    context_window,
    finding_replacement,
    fix_findings,
    flatten_candidates,
    formula_diff_reasons,
    formula_signature,
    remove_indices,
    removable,
    sanitize_fields,
    scan_row,
    scan_text,
    severity_counts,
    strip_junk,
    summarize,
    sure_removals,
)

#: Real-shaped records that must stay completely clean (math, Bangla, transliteration,
#: common symbols and HTML markup are all legitimate content).
CLEAN_SAMPLES = (
    'একটি বস্তু 5 m/s বেগে উপরে নিক্ষেপ করা হলো। নিচের কোনটি সঠিক?',
    'প্রকৃত তাপমাত্রা = 0°C+(51°C−4°C)×100/94 সুতরাং, প্রকৃত পাঠ 50°C।',
    r'$x^{2}+\theta$ এবং \(\sqrt{3}\) ও \[ \frac{1}{2} \] সমান',
    r'$$\begin{aligned} S &=\frac{W}{M \times V} \\ &=2.65 \mathrm{g} \end{aligned}$$ যেখানে',
    'জল <sub>2</sub> ও <br> বায়ু &times; 100',
    'ṛ ṭ ḍ ś ṣ ḥ ā ī ū ñ π θ λ Ω ± ≤ ≥ ≠ ≈ ∞ ∴ ∵ √ → ← ৳ ₹ ½ ⅓ ① ✓ ★ ☑ ● ■',
    '৫০°C তাপমাত্রায় 3.5×10⁻³ mol L⁻¹',
)


class CleanTextTests(SimpleTestCase):
    def test_clean_samples_report_nothing(self):
        for sample in CLEAN_SAMPLES:
            with self.subTest(sample=sample[:40]):
                self.assertEqual(scan_text(sample), [])

    def test_sentence_markers_are_not_special_characters(self):
        """A question mark, an exclamation mark … are normal text, never reported as junk."""
        samples = (
            'নিচের কোনটি সঠিক?',
            'দারুণ! সঠিক উত্তর দাও।',
            'a) ৫ b) ৬ c) ৭ d) ৮ — (i), (ii), (iii)',
            'তাহলে কি এটা ঠিক? হ্যাঁ! ঠিক আছে; নিশ্চিত।',
            'প্রশ্ন-১: 5% & 3*2 = 6, তাই "সঠিক" / "ভুল" (হ্যাঁ) [না] {ঠিক}',
            'ওজন < 5 kg > 2 kg; তাপমাত্রা = 0°C ~ 4°C',
            'প্রথম# দ্বিতীয়@ তৃতীয়_ চতুর্থ~ পঞ্চম| ষষ্ঠ\\ সপ্তম^ অষ্টম: নবম',
            'ক. ১  খ. ২   গ. ৩',
        )
        for sample in samples:
            with self.subTest(sample=sample[:40]):
                self.assertEqual(scan_text(sample), [])

    def test_clean_samples_are_never_stripped(self):
        for sample in CLEAN_SAMPLES:
            with self.subTest(sample=sample[:40]):
                self.assertEqual(strip_junk(sample), (sample, []))

    def test_bare_latex_is_only_informational(self):
        self.assertEqual(scan_text(r'V=\frac{4}{3}\pi r^{3}'), [])
        info = scan_text(r'V=\frac{4}{3}\pi r^{3}', include_info=True)
        self.assertEqual([f.kind for f in info], ['bare-latex'] * 2)

    def test_empty_and_non_string_input(self):
        self.assertEqual(scan_text(''), [])
        self.assertEqual(scan_text(None), [])
        self.assertEqual(scan_text(12345), [])
        self.assertEqual(strip_junk(None), ('', []))


class BrokenCharacterTests(SimpleTestCase):
    def test_replacement_control_and_bom_are_reported(self):
        found = scan_text('পদার্থ\ufffdবিজ্ঞান\x0c ও \ufeffগতি')
        self.assertEqual([f.code for f in found], [0xFFFD, 0x0C, 0xFEFF])
        self.assertEqual({f.kind for f in found}, {KIND_BROKEN, KIND_INVISIBLE})
        self.assertEqual(found[0].code_label, 'U+FFFD')
        self.assertEqual(found[0].severity, 'high')

    def test_strip_junk_removes_only_definite_junk(self):
        text = 'পদার্থ\ufffdবিজ্ঞান\u200b ও \ufeffগতি\x07'
        cleaned, removed = strip_junk(text)
        self.assertEqual(cleaned, 'পদার্থবিজ্ঞান ও গতি')
        self.assertEqual(len(removed), 4)
        self.assertEqual([f.code for f in removed], [0xFFFD, 0x200B, 0xFEFF, 0x07])

    def test_private_use_and_unassigned_are_stripped(self):
        text = 'ক\uE000খ\u0378গ'
        found = scan_text(text)
        self.assertEqual([f.kind for f in found], [KIND_BROKEN, KIND_BROKEN])
        cleaned, removed = strip_junk(text)
        self.assertEqual(cleaned, 'কখগ')
        self.assertEqual([f.code for f in removed], [0xE000, 0x0378])

    def test_tabs_and_newlines_are_kept(self):
        text = 'প্রথম লাইন\nদ্বিতীয়\tলাইন'
        self.assertEqual(scan_text(text), [])
        self.assertEqual(strip_junk(text), (text, []))

    def test_soft_hyphen_and_bidi_controls_are_stripped(self):
        cleaned, removed = strip_junk('গতি\u00ad না\u202b')
        self.assertEqual(cleaned, 'গতি না')
        self.assertEqual([f.code for f in removed], [0x00AD, 0x202B])

    def test_severity_counts_summarise_findings(self):
        counts = severity_counts(scan_text('ক\ufeffখ😀'))
        self.assertEqual(counts, {'medium': 2})


    def test_latex_escapes_are_not_stray_backslashes(self):
        samples = (
            r'$$\begin{array}{l}=\frac{0.5}{50} \mathrm{~mm} \\=0.01 \mathrm{~mm}\end{array}$$',
            r'$a \% b \& c \, d \; e \# f \_ g$',
            r'\begin{aligned}\mathrm{d} & =\mathrm{M}+\mathrm{C} \\& =4.87 \mathrm{~mm}\end{aligned}',
            'অনুপাত \\% নির্ণয় করা হয়েছে।',
        )
        for sample in samples:
            with self.subTest(sample=sample[:30]):
                self.assertEqual(scan_text(sample), [])

    def test_unbalanced_message_counts_the_dollar_signs(self):
        found = scan_text(r'মান $\boxed{x}$ ও $0.01 mm')
        self.assertEqual([f.kind for f in found], [KIND_MATH_UNBALANCED])
        self.assertIn('3 $ sign(s) in total', found[0].message)


class InvisibleAndSpaceTests(SimpleTestCase):
    def test_zero_width_joiner_and_non_joiner_are_reported(self):
        found = scan_text('ক\u200cষ\u200dণ')
        self.assertEqual([f.code for f in found], [0x200C, 0x200D])
        self.assertEqual([f.kind for f in found], [KIND_INVISIBLE, KIND_INVISIBLE])
        self.assertEqual(found[0].severity, 'low')      # ZWNJ can be intentional in Bangla
        self.assertEqual(found[1].severity, 'medium')

    def test_non_breaking_space_is_reported_but_kept(self):
        found = scan_text('৫\u00a0কেজি')
        self.assertEqual([f.kind for f in found], [KIND_SPACE])
        self.assertEqual(found[0].severity, 'low')
        self.assertEqual(strip_junk('৫\u00a0কেজি'), ('৫\u00a0কেজি', []))


class BanglaSignTests(SimpleTestCase):
    def test_stranded_vowel_sign_is_reported(self):
        text = 'সঠিক উত্তরটি ে বাছাই করো'
        found = scan_text(text)
        self.assertEqual([f.kind for f in found], [KIND_DANGLING])
        self.assertEqual(found[0].char, 'ে')
        self.assertEqual(found[0].severity, 'medium')

    def test_sign_at_the_start_of_the_field_is_reported(self):
        self.assertEqual([f.kind for f in scan_text('াকাশ')], [KIND_DANGLING])

    def test_two_vowel_signs_in_a_row_are_reported(self):
        found = scan_text('কিী')
        self.assertEqual([f.kind for f in found], [KIND_DOUBLE_SIGN])
        self.assertEqual(found[0].code, 0x09C0)

    def test_double_conjunct_sign_is_reported(self):
        found = scan_text('কন\u09cd\u09cdন')
        self.assertEqual([f.kind for f in found], [KIND_DOUBLE_SIGN])
        self.assertEqual(found[0].code, 0x09CD)

    def test_legacy_composed_vowel_signs_are_not_junk(self):
        for sample in ('কোঠা', 'ক\u09c7\u09beঠা', 'ক\u09c7\u09d7ঠা', 'বাংলাদেশের'):
            with self.subTest(sample=sample):
                self.assertEqual(scan_text(sample), [])

    def test_bangla_sign_after_inline_tag_is_not_junk(self):
        self.assertEqual(scan_text('ক<b>া</b>শ'), [])

    def test_trailing_conjunct_sign_is_reported_as_low(self):
        found = scan_text('রহস্য কর্।')
        self.assertEqual([f.kind for f in found], [KIND_DANGLING])
        self.assertEqual(found[0].severity, 'low')


class ForeignAndLookalikeTests(SimpleTestCase):
    def test_cyrillic_letter_that_imitates_latin_is_reported(self):
        found = scan_text('b\u043edy')
        self.assertEqual(found[0].kind, KIND_LOOKALIKE)
        self.assertEqual(found[0].severity, 'high')
        self.assertIn("'o'", found[0].message)

    def test_fullwidth_letters_digits_and_symbols_are_reported(self):
        found = scan_text('\uff21 5\uff0b3\uff1d8')
        self.assertEqual([f.kind for f in found], [KIND_LOOKALIKE] * 3)
        self.assertIn("'A'", found[0].message)
        self.assertIn("'+'", found[1].message)
        self.assertIn("'='", found[2].message)

    def test_mathematical_alphanumerics_are_reported(self):
        found = scan_text('\U0001d400\U0001d41a\U0001d7cf')
        self.assertEqual([f.kind for f in found], [KIND_LOOKALIKE] * 3)
        self.assertIn("'A'", found[0].message)
        self.assertIn("'a'", found[1].message)
        self.assertIn("'1'", found[2].message)

    def test_devanagari_and_cjk_letters_are_foreign(self):
        found = scan_text('প্রশ্ন क 中')
        self.assertEqual([f.kind for f in found], [KIND_FOREIGN, KIND_FOREIGN])
        self.assertIn('Devanagari-script', found[0].message)
        self.assertIn('CJK-script', found[1].message)

    def test_emoji_is_reported_but_never_stripped(self):
        text = 'সঠিক উত্তর 😀 টি'
        found = scan_text(text)
        self.assertEqual([f.kind for f in found], [KIND_EMOJI])
        self.assertEqual(found[0].code_label, 'U+1F600')
        self.assertEqual(strip_junk(text), (text, []))


class MathProtectionTests(SimpleTestCase):
    def test_math_is_never_modified_by_strip_junk(self):
        text = r'সূত্র: $\alpha\beta$ এবং \frac{1}{2} ও $$x^{2}$$'
        cleaned, removed = strip_junk(text + '\u200b')
        self.assertEqual(cleaned, text)
        self.assertEqual(len(removed), 1)
        self.assertEqual(scan_text(text), [])

    def test_broken_character_inside_math_is_reported_but_kept(self):
        text = 'মান $\\frac{1\ufffd2}$'
        found = scan_text(text)
        self.assertEqual([f.kind for f in found], [KIND_MATH_JUNK])
        self.assertEqual(found[0].code, 0xFFFD)
        self.assertEqual(found[0].severity, 'high')
        self.assertEqual(strip_junk(text), (text, []))

    def test_html_markup_is_whitelisted(self):
        text = '<p style="margin:0">জল</p><br><sub>2</sub>&times;'
        self.assertEqual(scan_text(text), [])
        cleaned, removed = strip_junk(text + '\ufeff')
        self.assertEqual(cleaned, text)
        self.assertEqual([f.code for f in removed], [0xFEFF])

    def test_unbalanced_delimiters_are_reported(self):
        found = scan_text('মান $x^{2} বেশি')
        self.assertEqual([f.kind for f in found], [KIND_MATH_UNBALANCED])
        self.assertEqual(found[0].severity, 'high')
        found = scan_text('মান $$x^{2} বেশি')
        self.assertEqual([f.kind for f in found], [KIND_MATH_UNBALANCED])
        found = scan_text(r'মান \(x^{2} বেশি')
        self.assertEqual([f.kind for f in found], [KIND_MATH_UNBALANCED])

    def test_inline_math_may_span_two_lines(self):
        self.assertEqual(scan_text('মান $x\n+y$\nবেশি'), [])


class FormulaGuardTests(SimpleTestCase):
    def test_signature_keeps_commands_delimiters_and_digits(self):
        commands, delimiters, digits = formula_signature(r'$\frac{12}{3}$ ও \sqrt{4}')
        self.assertEqual(dict(commands), {r'\frac': 1, r'\sqrt': 1})
        self.assertEqual(delimiters, (0, 2, 0, 0))
        self.assertEqual(digits, '1234')

    def test_signature_is_empty_for_plain_text(self):
        self.assertEqual(formula_signature('কোনো গণিত নেই'), ((), (0, 0, 0, 0), ''))

    def test_losses_are_reported(self):
        self.assertTrue(any('LaTeX command(s) lost' in r
                            for r in formula_diff_reasons(r'$\frac{1}{2}$', r'$1/2$')))
        self.assertTrue(any('reduced' in r
                            for r in formula_diff_reasons('$$x$$', 'x')))
        self.assertTrue(any('digits inside math' in r
                            for r in formula_diff_reasons('$12$', '$21$')))
        self.assertTrue(any('unbalanced' in r
                            for r in formula_diff_reasons('cost', 'cost $x')))

    def test_wrapping_bare_latex_in_dollars_is_not_a_loss(self):
        self.assertEqual(formula_diff_reasons(r'\frac{1}{2}', r'$\frac{1}{2}$'), [])
        self.assertEqual(formula_diff_reasons(r'$\theta$', r'$\theta$'), [])

    def test_untouched_formula_never_reports(self):
        text = r'$$\frac{1}{2}+\theta$$'
        self.assertEqual(formula_diff_reasons(text, text), [])


class SanitizeFieldsTests(SimpleTestCase):
    def test_junk_is_stripped_and_a_damaged_formula_is_reverted(self):
        row = {'question': r'মান $\frac{1}{2}$', 'option_1': 'ক) ৫\u200b'}
        cleaned = {'question': r'মান $1/2$', 'option_1': 'ক) ৫\u200b'}
        notes, stats = sanitize_fields(row, cleaned)
        self.assertEqual(cleaned['question'], row['question'])
        self.assertEqual(cleaned['option_1'], 'ক) ৫')
        self.assertEqual(stats['reverted'], ['question'])
        self.assertEqual(stats['removed'], 1)
        self.assertTrue(any('removed' in note for note in notes))
        self.assertTrue(any('reverted' in note for note in notes))

    def test_clean_reply_untouched(self):
        row = {'question': 'সঠিক প্রশ্ন?', 'explanation': 'সঠিক ব্যাখ্যা।'}
        cleaned = dict(row)
        notes, stats = sanitize_fields(row, cleaned)
        self.assertEqual(notes, [])
        self.assertEqual(stats, {'removed': 0, 'reverted': []})
        self.assertEqual(cleaned, row)

    def test_missing_field_is_skipped(self):
        row = {'question': 'ক', 'explanation': '$x$'}
        cleaned = {'question': 'খ'}
        sanitize_fields(row, cleaned)
        self.assertEqual(cleaned, {'question': 'খ'})

    def test_field_list_limits_the_check(self):
        row = {'question': '$x$', 'explanation': 'ব\u200b'}
        cleaned = {'question': '$x$', 'explanation': 'ব\u200b'}
        sanitize_fields(row, cleaned, fields=['question'])
        self.assertEqual(cleaned['explanation'], 'ব\u200b')
        self.assertEqual(cleaned['question'], '$x$')


class RowScanTests(SimpleTestCase):
    def test_scan_row_covers_every_question_and_meta_field(self):
        from cheradip.question_updater import _META_FIELDS, _QUESTION_FIELDS
        expected = set(_QUESTION_FIELDS) | set(_META_FIELDS) | {'explanation2', 'explanation3'}
        self.assertTrue(expected.issubset(set(SCAN_FIELDS)))
        row = {field: 'ঠিক\u200b' for field in sorted(expected)}
        found = scan_row(row, sorted(expected))
        self.assertEqual(set(found), expected)

    def test_scan_row_returns_only_dirty_fields(self):
        row = {'question': 'ঠিক?', 'option_1': 'ক\u200b', 'chapter': 'প্রথম'}
        found = scan_row(row)
        self.assertEqual(list(found), ['option_1'])


class CandidatePromptTests(SimpleTestCase):
    def test_candidates_are_numbered_per_field_with_context(self):
        row = {
            'question': 'পদার্থ\u200bবিজ্ঞান?',
            'option_1': 'ক) ৫\u200b°C',
            'chapter': 'তৃতীয়',
        }
        findings = scan_row(row)
        lines, ordered = build_prompt_block(row, findings)
        text = '\n'.join(lines)
        # Only the fields that really hold a suspicious code point are listed.
        self.assertEqual(list(findings), ['question', 'option_1'])
        self.assertEqual([field for field, _item in ordered], ['question', 'option_1'])
        self.assertIn('CANDIDATE CODE POINTS', text)
        self.assertIn('  1. question @6 U+200B ZERO WIDTH SPACE', text)
        self.assertIn('  2. option_1 @4 U+200B ZERO WIDTH SPACE', text)
        self.assertIn('[HERE]', text)
        self.assertIn('KEEP (never list them)', text)
        self.assertIn('LaTeX / KaTeX / MathJax', text)
        self.assertIn('{"remove"', text)
        self.assertNotIn('chapter', text)

    def test_clean_record_has_no_candidates(self):
        row = {'question': 'সঠিক প্রশ্ন?', 'option_1': 'ক'}
        lines, ordered = build_prompt_block(row, scan_row(row))
        self.assertEqual((lines, ordered), ([], []))

    def test_candidate_lines_spell_out_invisible_code_points(self):
        row = {'question': 'ক\u200bখ'}
        ordered = flatten_candidates(scan_row(row))
        line = candidate_lines(ordered, row)[0]
        self.assertIn('U+200B ZERO WIDTH SPACE', line)
        self.assertIn('"ক[HERE]খ"', line)

    def test_summarize_groups_repeated_code_points(self):
        line = summarize(scan_text('ক\u200bখ\u200bগ\ufeff'))
        self.assertIn('U+200B ZERO WIDTH SPACE ×2', line)
        self.assertIn('U+FEFF', line)
        self.assertIn('invisible', line)


class CharacterFixTests(SimpleTestCase):
    """``fix_findings`` may only take out characters — never a word, space or sentence."""

    def test_fix_findings_takes_out_only_the_found_characters(self):
        text = 'পদার্থ\u200bবিজ্ঞান\u0421'
        cleaned, applied = fix_findings(text, scan_text(text))
        self.assertEqual(cleaned, 'পদার্থবিজ্ঞান')
        self.assertIn('পদার্থবিজ্ঞান', cleaned)
        self.assertEqual([f.code for f in applied], [0x200B, 0x0421])

    def test_fix_findings_replaces_a_special_space_instead_of_gluing_words(self):
        text = '৫\u00a0কেজি'
        cleaned, applied = fix_findings(text, scan_text(text))
        self.assertEqual(cleaned, '৫ কেজি')
        self.assertEqual(finding_replacement(applied[0]), ' ')

    def test_fix_findings_ignores_a_stale_finding(self):
        text = 'সঠিক পাঠ'
        self.assertEqual(fix_findings(text, scan_text('ক\u200bখ')), (text, []))

    def test_remove_indices_and_sure_removals(self):
        text = 'ক\u200bখ\ufeffগ😀'
        self.assertEqual(remove_indices(text, [1, 2]), ('ক\ufeffগ😀', 2))
        sure = sure_removals(scan_text(text))
        self.assertEqual([f.code for f in sure], [0x200B, 0xFEFF])   # the emoji needs the AI/human

    def test_context_window_marks_the_character_and_spells_out_invisible_ones(self):
        self.assertIn('পদার্থ[HERE]বিজ্ঞান', context_window('পদার্থ\u200bবিজ্ঞান', 6))
        # Every other invisible code point of the window is spelled out as well.
        self.assertEqual(context_window('ক\u200bখ\u200bগ', 1), 'ক[HERE]খ<U+200B>গ')
        self.assertTrue(context_window('x' * 60 + '\u200b', 60).startswith('…'))

    def test_script_and_style_blocks_are_shielded(self):
        html = '<script>var a = "\u2192";</script><style>.x{color:#f00}~</style>ঠিক?'
        self.assertEqual(scan_text(html), [])

    def test_unbalanced_math_is_reported_but_never_removable(self):
        """A stray ``$`` is a check-this item: deleting it could damage a working formula."""
        found = scan_text('মান $x^{2} বেশি')
        self.assertEqual([f.kind for f in found], [KIND_MATH_UNBALANCED])
        self.assertEqual(removable(found), [])
        self.assertEqual(sure_removals(found), [])


class UpdaterWiringTests(SimpleTestCase):
    def test_special_prompt_asks_only_for_characters(self):
        from cheradip.question_updater import _build_special_prompt
        row = {'question': 'পদার্থ\u200bবিজ্ঞান?', 'option_1': 'ক', 'level_tr': 'HSC',
               'class_level': '11-12', 'subject': 'পদার্থবিজ্ঞান', 'qid': '101'}
        prompt, candidates = _build_special_prompt(row, scan_row(row))
        self.assertIn('Bangladesh national curriculum', prompt)
        self.assertIn('qid: 101', prompt)
        self.assertIn('Do NOT correct spelling, grammar, wording, punctuation or word spacing', prompt)
        self.assertIn('  1. question @6 U+200B ZERO WIDTH SPACE', prompt)
        self.assertIn('KEEP (never list them)', prompt)
        self.assertIn('LaTeX / KaTeX / MathJax', prompt)
        self.assertEqual([item.code for _field, item in candidates], [0x200B])

    def test_correction_prompt_is_bangladesh_specific_and_keeps_math(self):
        from cheradip.question_updater import _build_correction_prompt
        row = {'question': r'মান $\frac{1}{2}$?', 'option_1': 'ক', 'level_tr': 'HSC', 'qid': '7'}
        prompt = _build_correction_prompt(row)
        self.assertIn('Bangladesh education system', prompt)
        self.assertIn('Bangla medium', prompt)
        self.assertIn('"question"', prompt)
        self.assertIn('LaTeX / KaTeX / MathJax', prompt)
        self.assertIn('{"questions":', prompt)
        self.assertIn('word spacing', prompt)

    def test_normalize_kind_maps_the_legacy_names(self):
        from cheradip.question_updater import KIND_CLOUD, KIND_SPECIAL, normalize_kind
        self.assertEqual(normalize_kind('special'), KIND_SPECIAL)
        self.assertEqual(normalize_kind('CLOUD'), KIND_CLOUD)
        self.assertEqual(normalize_kind('question'), KIND_CLOUD)      # legacy button value
        self.assertEqual(normalize_kind('explanation'), KIND_CLOUD)
        self.assertEqual(normalize_kind('nonsense'), '')
        self.assertEqual(normalize_kind(None), '')

    def test_confirm_removals_maps_answer_numbers_to_characters(self):
        from cheradip import question_updater as qu
        row = {'question': 'পদার্থ\u200bবিজ্ঞান\u0421', 'option_1': 'ক\u200bখ'}
        findings = scan_row(row)
        reply = ({'remove': {'question': [1], 'option_1': [3]}}, 'home-ai')
        with mock.patch.object(qu, '_ask_special', return_value=reply):
            confirmed, provider = qu._confirm_removals(row, findings)
        self.assertEqual(provider, 'home-ai')
        self.assertEqual({field: [item.code for item in items] for field, items in confirmed.items()},
                         {'question': [0x200B], 'option_1': [0x200B]})

    def test_confirm_removals_ignores_unusable_answers(self):
        from cheradip import question_updater as qu
        row = {'question': 'পদার্থ\u200bবিজ্ঞান'}
        findings = scan_row(row)
        for reply in ([99], {'remove': {'option_2': [1]}}, 'not json'):
            with self.subTest(reply=reply):
                with mock.patch.object(qu, '_ask_special', return_value=(reply, 'home-ai')):
                    confirmed, _provider = qu._confirm_removals(row, findings)
                self.assertEqual(confirmed, {})

    def test_confirm_removals_reports_an_unreachable_ai(self):
        from cheradip import question_updater as qu
        row = {'question': 'পদার্থ\u200bবিজ্ঞান'}
        findings = scan_row(row)
        with mock.patch.object(qu, '_ask_special', return_value=(None, None)):
            self.assertEqual(qu._confirm_removals(row, findings), (None, None))

    def test_updater_sanitize_wrapper_reports_its_notes(self):
        from cheradip.question_updater import _sanitize_fields
        row = {'question': r'মান $\frac{1}{2}$', 'option_1': 'ক) ৫\u200b'}
        cleaned = {'question': r'মান $1/2$', 'option_1': 'ক) ৫\u200b'}
        notes, stats = _sanitize_fields(row, cleaned, ('question', 'option_1'))
        self.assertEqual(cleaned['question'], row['question'])
        self.assertEqual(cleaned['option_1'], 'ক) ৫')
        self.assertEqual(stats['reverted'], ['question'])
        self.assertTrue(notes)

    def test_updater_sanitize_wrapper_follows_the_given_fields(self):
        from cheradip.question_updater import _sanitize_fields
        row = {'question': 'ক\u200b', 'explanation': 'খ\u200b'}
        cleaned = {'explanation': 'খ\u200b', 'question': 'ক\u200b'}
        _sanitize_fields(row, cleaned, ('explanation',))
        self.assertEqual(cleaned['explanation'], 'খ')
        self.assertEqual(cleaned['question'], 'ক\u200b')


class SpecialPassTests(SimpleTestCase):
    """The Home AI character pass changes characters only — never words or sentences."""

    ROW = {'question': 'পদার্থ\u200bবিজ্ঞান?', 'option_1': 'ক\u0421', 'qid': '101',
           'level_tr': 'HSC', 'class_level': '11-12', 'subject': 'পদার্থবিজ্ঞান'}

    def test_unwanted_characters_are_taken_out(self):
        from cheradip import question_updater as qu
        row = dict(self.ROW)
        reply = ({'remove': {'option_1': [1]}}, 'home-ai')   # the ZWSP is definitely broken
        with mock.patch.object(qu, '_ask_special', return_value=reply):
            cleaned, removals, provider, stats = qu._special_clean(row, qu._HYGIENE_FIELDS)
        self.assertEqual(provider, 'home-ai')
        self.assertEqual(cleaned['question'], 'পদার্থবিজ্ঞান?')
        self.assertEqual(cleaned['option_1'], 'ক')
        self.assertEqual(stats['findings'], 2)
        self.assertEqual(stats['sure'], 1)
        self.assertEqual(stats['ai'], 1)
        self.assertEqual(stats['removed'], 2)
        self.assertEqual(stats['kept'], 0)
        self.assertFalse(stats['unverified'])
        self.assertEqual(sorted(removals), ['option_1', 'question'])
        self.assertEqual(row, self.ROW)                       # the source row is never modified

    def test_field_kept_by_the_ai_leaves_the_record_unchanged(self):
        from cheradip import question_updater as qu
        row = {'question': 'পদার্থ\u0421বিজ্ঞান?', 'qid': '102', 'level_tr': 'HSC'}
        with mock.patch.object(qu, '_ask_special', return_value=({'remove': {}}, 'home-ai')):
            cleaned, removals, _provider, stats = qu._special_clean(row, qu._HYGIENE_FIELDS)
        self.assertIsNone(cleaned)
        self.assertEqual(removals, {})
        self.assertEqual(stats['kept'], 1)

    def test_definitely_broken_code_points_need_no_ai(self):
        from cheradip import question_updater as qu
        row = {'question': 'পদার্থ\ufffdবিজ্ঞান?', 'qid': '103', 'level_tr': 'HSC'}
        with mock.patch.object(qu, '_ask_special') as fake:
            cleaned, _removals, provider, stats = qu._special_clean(row, qu._HYGIENE_FIELDS)
        fake.assert_not_called()
        self.assertEqual(cleaned['question'], 'পদার্থবিজ্ঞান?')
        self.assertIsNone(provider)
        self.assertEqual(stats['sure'], 1)

    def test_unreachable_home_ai_keeps_the_definitely_broken_ones(self):
        from cheradip import question_updater as qu
        row = {'question': 'পদার্থ\u200bবিজ্ঞান\u0421', 'qid': '104', 'level_tr': 'HSC'}
        with mock.patch.object(qu, '_ask_special', return_value=(None, None)):
            cleaned, _removals, _provider, stats = qu._special_clean(row, qu._HYGIENE_FIELDS)
        self.assertEqual(cleaned['question'], 'পদার্থবিজ্ঞান\u0421')
        self.assertTrue(stats['unverified'])

    def test_clean_record_queues_nothing(self):
        from cheradip import question_updater as qu
        row = {'question': 'নিচের কোনটি সঠিক?', 'qid': '105', 'level_tr': 'HSC'}
        with mock.patch.object(qu, '_ask_special') as fake:
            cleaned, removals, provider, stats = qu._special_clean(row, qu._HYGIENE_FIELDS)
        fake.assert_not_called()
        self.assertIsNone(cleaned)
        self.assertEqual(removals, {})
        self.assertIsNone(provider)
        self.assertEqual(stats['findings'], 0)

    def test_payload_marks_the_removed_characters_and_keeps_the_clean_text(self):
        from backend.database_admin_views import _strip_red_markup
        from cheradip import question_updater as qu
        row = {'qid': '101', 'question': 'পদার্থ\u200bবিজ্ঞান?', 'option_1': 'ক',
               'level_tr': 'HSC', 'class_level': '11-12'}
        findings = scan_row(row)
        payload = qu._build_payload(row, {'question': 'পদার্থবিজ্ঞান?'}, qu.KIND_SPECIAL,
                                    'tbl', removals={'question': findings['question']})
        value = payload['question']
        self.assertTrue(value.startswith('<!--CERADIP_PLAIN:'))
        self.assertIn('<del', value)          # the review page renders it as marked-up HTML
        self.assertIn('U+200B', value)        # … and names the character that is taken out
        self.assertEqual(_strip_red_markup(value), 'পদার্থবিজ্ঞান?')
        self.assertNotIn('\u200b', _strip_red_markup(value))
        self.assertEqual(payload['option_1'], 'ক')
        self.assertEqual(payload['qid'], '101')
        self.assertEqual(payload['status'], 'Update')

    def test_correction_payload_uses_the_word_diff(self):
        from cheradip import question_updater as qu
        row = {'qid': '7', 'question': 'নিচের কোনটি সঠিক?', 'level_tr': 'HSC'}
        payload = qu._build_payload(row, {'question': 'নিখুঁত উত্তর?'}, qu.KIND_CLOUD, 'tbl')
        self.assertTrue(payload['question'].startswith('<!--CERADIP_PLAIN:'))
        self.assertIn('<del', payload['question'])

    def test_special_summary_message_mentions_counts_and_examples(self):
        from collections import Counter
        from cheradip.question_updater import _special_summary
        msg = _special_summary({
            'findings': 3, 'fields': 2, 'rows': 2, 'removed': 2, 'kept': 1, 'unverified': 1,
            'codes': Counter({(0x200B, 'ZERO WIDTH SPACE'): 2,
                              (0x0421, 'CYRILLIC CAPITAL LETTER ES'): 1}),
            'samples': [('101', 'option_1', 'U+200B ZERO WIDTH SPACE @0')],
        })
        self.assertIn('3 code point(s) in 2 field(s) of 2 record(s)', msg)
        self.assertIn('U+200B ZERO WIDTH SPACE x2', msg)
        self.assertIn('2 taken out', msg)
        self.assertIn('1 kept', msg)
        self.assertIn('1 record(s) could not be checked', msg)
        self.assertIn('qid 101', msg)
        self.assertEqual(_special_summary({'findings': 0}), '')
        self.assertEqual(_special_summary({}), '')

    def test_job_rejects_an_unknown_kind(self):
        from cheradip.question_updater import run_question_update_job
        self.assertIn('Unknown update kind',
                      run_question_update_job('default', 'tbl', 'bogus')['message'])
        self.assertIn('Unknown update kind',
                      run_question_update_job('default', 'tbl', '')['message'])

    def test_unbalanced_math_delimiter_is_reported_not_removed(self):
        from cheradip import question_updater as qu
        row = {'question': 'মান $x^{2} বেশি?', 'qid': '106', 'level_tr': 'HSC'}
        with mock.patch.object(qu, '_ask_special') as fake:
            cleaned, removals, _provider, stats = qu._special_clean(row, qu._HYGIENE_FIELDS)
        fake.assert_not_called()              # a stray $ is not even offered to the AI
        self.assertIsNone(cleaned)
        self.assertEqual(removals, {})
        self.assertEqual(stats['check'], 1)
        self.assertEqual(stats['removed'], 0)

    def test_summary_mentions_the_manual_math_check(self):
        from cheradip.question_updater import _special_summary
        msg = _special_summary({'findings': 1, 'fields': 1, 'rows': 1, 'removed': 0, 'kept': 1,
                                'check': 1})
        self.assertIn('manual check', msg)
        self.assertIn('never', msg)




