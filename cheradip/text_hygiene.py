"""
Whitelist-aware "unwanted special character" detection for question text.

Scope: this module only looks for *characters* that do not belong to a Bangla/English exam
question. It never corrects words, sentences, spelling, grammar or spacing — that is the
Cloud AI "AI Update" pass in ``cheradip.question_updater``.

* :func:`scan_text` reports the code points that cannot belong to a Bangla/English exam
  question — control/invisible characters, U+FFFD, private-use/unassigned code points,
  emoji, letters borrowed from another script (Cyrillic / full-width / mathematical
  look-alikes), stray or doubled Bangla dependent signs, unusual spaces, unbalanced math
  delimiters and junk inside a formula.
* :func:`fix_findings` applies the accepted findings: a finding is deleted, a special space
  is replaced by a normal space (so words never glue together). Every other character — and
  therefore every word and every sentence — is copied byte-for-byte.
* :func:`build_prompt_block` hands the Home AI the numbered candidates plus the rules that say
  what is *not* a special character; :func:`sure_removals` lists the code points that are broken
  beyond doubt, so they need no AI opinion at all. An unbalanced math delimiter is never offered
  as a removal (:data:`REPORT_ONLY_KINDS`) — the stray ``$`` may as well be a missing one — it is
  only reported for the admin to check.
* :func:`sanitize_fields` post-checks a Cloud AI correction: it reverts a field whose
  formula was damaged (:func:`formula_diff_reasons`).

Never reported (the whitelist):

* Bangla (U+0980-U+09FF), ASCII letters/digits and the normal punctuation of a sentence
  (``? ! . , ; : " ' - ( ) [ ] { } / % & * + = < >``), Latin-1/Extended transliteration
  letters (ā ī ū ṛ ṭ ḍ ś ṣ ḥ ñ), Greek letters, super/subscripts, currency signs and the
  symbols school books really use (× ÷ ± ≤ ≥ ≠ ≈ ∞ ∴ ∵ ∠ ° √ → ← • ৳ ₹ ½ …). A question mark,
  an exclamation mark and every other marker of the sentence is normal text, not junk.
* Math exactly as the render pipeline understands it — the ``$$…$$``, ``$…$``, ``\\(…\\)``,
  ``\\[…\\]`` delimiters and the LaTeX / KaTeX / MathJax commands handled by
  ``cheradip.export_question_katex`` (mirror of ``fcheradip question-katex-render.ts``).
  Inside a formula only characters that break KaTeX outright are reported, and nothing
  inside math is ever removed or rewritten.
* HTML markup/entities (``<br>``, ``<sub>``, ``&times;``) and whole ``<script>`` /
  ``<style>`` blocks — imported questions contain them and the exporter shields them too
  (``_FORMAT_SHIELD_RE``).

Only :data:`AUTO_STRIP_CODES` is removed without asking the AI; every other finding is
listed for the Home AI, and the result is always queued as a pending request that a human
approves. A junk character is never a reason to touch the words around it — the fix is
always "take out the character, keep the word".
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

__all__ = [
    'Finding',
    'CONTENT_FIELDS',
    'TEXT_FIELDS',
    'SCAN_FIELDS',
    'AUTO_STRIP_CODES',
    'ALLOWED_RANGES',
    'ALLOWED_EXTRA',
    'INFO_KINDS',
    'REPORT_ONLY_KINDS',
    'PROMPT_RULE',
    'REMOVE_RULE',
    'KEEP_RULE',
    'MATH_RULE',
    'ANSWER_RULE',
    'scan_text',
    'scan_row',
    'summarize',
    'severity_counts',
    'context_window',
    'flatten_candidates',
    'candidate_lines',
    'build_prompt_block',
    'finding_replacement',
    'fix_findings',
    'remove_indices',
    'sure_removals',
    'removable',
    'strip_junk',
    'formula_signature',
    'formula_diff_reasons',
    'sanitize_fields',
]


class Finding(NamedTuple):
    """One suspicious character found in a field."""

    index: int      # offset of the character inside the field text
    char: str       # the character itself
    code: int       # its ordinal (code point)
    name: str       # unicodedata name (or a 'UNASSIGNED…' style fallback)
    category: str   # unicodedata category, e.g. 'Cf', 'So', 'Mn', 'Lu'
    kind: str       # see the KIND_* constants
    severity: str   # 'high' | 'medium' | 'low'
    message: str    # human readable explanation

    @property
    def code_label(self) -> str:
        """``'U+200B'`` — the label used in admin messages and in the AI prompt."""
        return 'U+%04X' % self.code


# ------------------------------------------------------------------- kinds ---
KIND_BROKEN = 'broken-codepoint'      # U+FFFD, control, private-use, unassigned, surrogate
KIND_INVISIBLE = 'invisible'          # zero-width / bidi / soft hyphen
KIND_EMOJI = 'emoji'
KIND_SYMBOL = 'unusual-symbol'
KIND_SPACE = 'unusual-space'
KIND_FOREIGN = 'foreign-letter'       # letter from another script (Devanagari, CJK, …)
KIND_LOOKALIKE = 'look-alike'         # Cyrillic / full-width / mathematical ASCII clone
KIND_DANGLING = 'dangling-sign'       # Bangla sign with no letter to attach to
KIND_DOUBLE_SIGN = 'double-sign'      # two Bangla vowel signs in a row
KIND_MATH_JUNK = 'math-junk'          # char that breaks KaTeX inside a formula
KIND_MATH_UNBALANCED = 'math-unbalanced'
KIND_BARE_LATEX = 'bare-latex'        # informational only (the renderer re-wraps it)

#: Findings that are informational only (the render pipeline already copes with them, e.g.
#: ``KIND_BARE_LATEX``); :func:`scan_text` returns them just when ``include_info=True``.
INFO_KINDS = (KIND_BARE_LATEX,)

#: Findings that are only *reported*, never turned into a pending removal: an unbalanced math
#: delimiter is a "check this" item — the stray sign may just as well be a missing one, so deleting
#: it could damage a working formula. They appear in the job message, in the read-only
#: ``manage.py scan_question_junk`` report and in :func:`summarize`, but never in a removal.
REPORT_ONLY_KINDS = (KIND_MATH_UNBALANCED,)

# ------------------------------------------------------------------- fields ---
#: Fields whose text the AI proofreader rewrites (mirrors question_updater._QUESTION_FIELDS
#: + explanation2/3).
CONTENT_FIELDS = (
    'question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer',
    'explanation', 'explanation2', 'explanation3',
)
#: Visible-text metadata (mirrors question_updater._META_FIELDS).
TEXT_FIELDS = (
    'subject', 'subject_tr', 'chapter_no', 'chapter', 'topic_no', 'topic',
    'type', 'level', 'subsource',
)
#: Default field list for :func:`scan_row` — every text field of a question record.
SCAN_FIELDS = CONTENT_FIELDS + TEXT_FIELDS


# ------------------------------------------------------------- whitelist ----
#: Code point ranges that are always legitimate in a Bangla/English question field.
ALLOWED_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0020, 0x007E),   # printable ASCII (letters, digits, punctuation)
    (0x00A1, 0x00FF),   # Latin-1 letters + × ÷ ± ° µ ½ ¼ ¾ ¿ « »
    (0x0100, 0x024F),   # Latin Extended-A/B (ā ī ū ṛ ṇ ṭ ḍ ś ṣ ḥ ñ ç ø)
    (0x02B0, 0x02FF),   # spacing modifier letters (ˉ ˘ ˆ ˜ ˚) used as accents
    (0x0300, 0x036F),   # combining diacritical marks (IAST macron / dot below)
    (0x0370, 0x03FF),   # Greek (α β θ λ μ π σ φ ω Ω Σ Δ)
    (0x0980, 0x09FF),   # Bangla (letters, digits, signs, ৳)
    (0x1E00, 0x1EFF),   # Latin Extended Additional (ḷ ṭ ẖ ṣ)
    (0x2010, 0x2027),   # – — ‘ ’ “ ” „ † ‡ • ‣ …
    (0x2030, 0x205E),   # ‰ ′ ″ ‹ › ⁄ ※
    (0x2070, 0x209F),   # super/subscripts (¹²³ ₀₁₂)
    (0x20A0, 0x20BF),   # currency (₹ ₨ ¢ £ € ¥)
    (0x2100, 0x218F),   # letterlike symbols + number forms (ℓ ℎ № ℃ ⅓)
    (0x2190, 0x22FF),   # arrows + mathematical operators (→ ≤ ∑ ∫ √ ∞ ∴ ∵ ∠ ∈)
    (0x2460, 0x24FF),   # enclosed alphanumerics (① ⒈ Ⓐ) used as option markers
    (0x25A0, 0x25FF),   # geometric shapes (● ○ ■ □ ▲ ◆) used as option bullets
)

#: Individual characters outside the ranges above that school questions really use.
#: ``।``/``॥`` (U+0964/U+0965) are the Bangla sentence enders — they live in the Devanagari
#: block but are shared with Bangla, so they must never be reported as foreign.
ALLOWED_EXTRA = frozenset('⌈⌉⌊⌋★☆☐☑☒✓✔✗✘।॥')

#: Bangla dependent signs — only valid when a letter of the same word precedes them.
_BANGLA_MIN, _BANGLA_MAX = 0x0980, 0x09FF
_BANGLA_HASANTA = 0x09CD
_BANGLA_VOWEL_SIGNS = frozenset(list(range(0x09BE, 0x09CD)) + [0x09D7])
_BANGLA_SIGNS = frozenset(
    list(range(0x09BE, 0x09CE))
    + [0x0981, 0x0982, 0x0983, 0x09BC, 0x09D7, 0x09E2, 0x09E3, 0x09FE]
)
_BANGLA_LETTER_RE = re.compile('[\u0985-\u0994\u0995-\u09B9\u09CE\u09DC\u09DD\u09DF-\u09E1\u09F0\u09F1]')

#: Legacy decompositions that are valid Bangla (ো = ে+া, ৌ = ে+ৗ in older data).
_BANGLA_COMPOSED_OK = frozenset(['\u09C7\u09BE', '\u09C7\u09D7'])

#: Cyrillic letters that silently imitate Latin ones (NFKC does not fold these).
_CYRILLIC_LOOKALIKE = {
    '\u0430': 'a', '\u0435': 'e', '\u043E': 'o', '\u0441': 'c', '\u0440': 'p',
    '\u0445': 'x', '\u0443': 'y', '\u0456': 'i', '\u0458': 'j', '\u04BB': 'h',
    '\u0410': 'A', '\u0412': 'B', '\u0415': 'E', '\u041A': 'K', '\u041C': 'M',
    '\u041D': 'H', '\u041E': 'O', '\u0420': 'P', '\u0421': 'C', '\u0422': 'T',
    '\u0425': 'X', '\u0423': 'Y', '\u0406': 'I', '\u0408': 'J',
}

#: Code points that are broken beyond doubt, so :func:`strip_junk` may delete them.
#: ``\t``/``\n``/``\r`` are deliberately kept. U+200C (ZWNJ) is *not* here: in Bangla it can
#: be intentional (it blocks a conjunct), so it is only reported for the AI/human to decide.
AUTO_STRIP_CODES = frozenset(
    [0x00AD, 0x180E, 0x200B, 0x200D, 0x200E, 0x200F, 0xFEFF, 0xFFFD]
    + list(range(0x202A, 0x202F))   # bidi embedding / override
    + list(range(0x2060, 0x2065))   # word joiner / invisible separators
    + list(range(0x2066, 0x206A))   # bidi isolates
)

_HTML_TAG_RE = re.compile(r'<!--[\s\S]*?-->|</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>')
#: Whole ``<script>…</script>`` / ``<style>…</style>`` blocks: the body is code, never question
#: text, so every code point of it is protected like an HTML tag.
_SHIELD_BLOCK_RE = re.compile(r'<(script|style)\b[^>]*>[\s\S]*?</\1\s*>', re.I)
_HTML_ENTITY_RE = re.compile(r'&(?:[A-Za-z][A-Za-z0-9]{1,31}|#\d{1,7}|#[xX][0-9A-Fa-f]{1,6});')
_LATEX_COMMAND_RE = re.compile(r'\\[A-Za-z]+')
#: Characters LaTeX may escape (``\\`` line break, ``\%``, ``\&``, ``\,``, ``\ ``, ``\|`` …).
_LATEX_ESCAPES = frozenset('\\%$&#_{}()[]|,;:!~^ \t-')
_CONTROL_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')

_CATEGORY_FALLBACK = {
    'Cc': 'CONTROL CHARACTER',
    'Cf': 'FORMAT CHARACTER',
    'Cn': 'UNASSIGNED CODE POINT',
    'Co': 'PRIVATE USE CODE POINT',
    'Cs': 'SURROGATE CODE POINT',
}


def _char_name(ch: str) -> str:
    """Unicode name of a character, with a readable fallback for unnamed code points."""
    try:
        name = unicodedata.name(ch)
    except ValueError:
        name = ''
    return name or _CATEGORY_FALLBACK.get(unicodedata.category(ch), 'UNKNOWN CHARACTER')


def _in_allowed_range(code: int) -> bool:
    for low, high in ALLOWED_RANGES:
        if code < low:
            return False
        if code <= high:
            return True
    return False


def _lookalike(ch: str) -> str:
    """The plain ASCII character this code point silently imitates ('' when it imitates none).

    Catches the classic "extra letter" bugs: Cyrillic а/е/о/с/р/х inside English words,
    full-width ＡＢＣ ／ ＝ and the mathematical alphanumeric 𝐀 𝐚 𝟏 forms.
    """
    if ch in _CYRILLIC_LOOKALIKE:
        return _CYRILLIC_LOOKALIKE[ch]
    folded = unicodedata.normalize('NFKC', ch)
    if folded != ch and folded.isascii() and not folded.isspace():
        return folded
    return ''


def _is_emoji(code: int) -> bool:
    """Emoji / pictograph / dingbat blocks (the symbols that are pure noise in a question)."""
    return (0x1F000 <= code <= 0x1FAFF) or (0x2B00 <= code <= 0x2BFF) or (0x2600 <= code <= 0x27BF)


def _script_name(ch: str) -> str:
    """Script label of a character (``'Devanagari'``, ``'CJK'``) for the finding messages."""
    name = _char_name(ch)
    if name.startswith('CJK'):
        return 'CJK'
    return name.split(' ')[0].title()


def _finding(index: int, text: str, severity: str, kind: str, message: str) -> Finding:
    """Build a :class:`Finding` for the character at ``index``."""
    ch = text[index]
    return Finding(index, ch, ord(ch), _char_name(ch), unicodedata.category(ch), kind,
                   severity, message)


def _group_end(text: str, start: int, opener: str) -> int:
    """Offset just past the group opened at ``start`` (-1 when it never closes)."""
    closer = {'{': '}', '[': ']', '(': ')'}[opener]
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            i += 2
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _latex_run_end(text: str, i: int) -> int:
    """Offset just past the LaTeX token starting at the backslash ``i``.

    Covers a command name plus everything glued to it — ``\\frac{a}{b}``, ``\\sqrt[3]{x}``,
    ``\\theta_1``, ``x^{2}`` — and the two-character escapes (``\\\\``, ``\\%``, ``\\,``,
    ``\\ ``), so a whole formula token is protected as one unit and a legitimate LaTeX line
    break is never mistaken for a stray backslash.
    """
    m = _LATEX_COMMAND_RE.match(text, i)
    if not m:
        return min(i + 2, len(text))      # \\, \%, \,, \<space> … or a lone backslash
    j = m.end()
    while True:
        k = j
        while k < len(text) and text[k] in ' \t':
            k += 1
        if k < len(text) and text[k] in '{[(':
            end = _group_end(text, k, text[k])
            if end < 0:
                return len(text)
            j = end
            continue
        if k < len(text) and text[k] in '^_':
            k += 1
            if k < len(text) and text[k] in '{[(':
                end = _group_end(text, k, text[k])
                if end < 0:
                    return len(text)
                j = end
                continue
            if k < len(text):
                if text[k] == '\\':
                    j = _latex_run_end(text, k)
                elif not text[k].isspace():
                    j = k + 1
                continue
        break
    return j


def _inline_dollar_close(text: str, i: int) -> int:
    """Offset of the ``$`` closing the inline math opened at ``i`` (-1 when unterminated).

    A newline may appear inside (the KaTeX renderer walks ``$…$`` across lines as well), so a
    formula wrapped over two lines is never mistaken for stray dollar signs.
    """
    p = i + 1
    while p < len(text):
        ch = text[p]
        if ch == '\\':
            p += 2
            continue
        if ch == '$':
            if p + 1 < len(text) and text[p + 1] == '$':
                p += 2
                continue
            return p
        p += 1
    return -1


def _scan_spans(text: str, include_info: bool = False):
    """Protected spans + the findings that come from the delimiters themselves.

    A span is ``(start, end, kind, opener)`` with ``kind`` one of ``'math'`` (``$$…$$``,
    ``$…$``, ``\\(…\\)``, ``\\[…\\]`` — the delimiters ``export_question_katex`` renders),
    ``'latex'`` (bare LaTeX command run) or ``'html'`` (tag / entity). Nothing inside a span
    is ever treated as junk, except the code points that break KaTeX (see :func:`_classify`).
    """
    spans: List[Tuple[int, int, str, str]] = []
    findings: List[Finding] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '<':
            m = _SHIELD_BLOCK_RE.match(text, i)
            if m:
                spans.append((i, m.end(), 'html', '<'))
                i = m.end()
                continue
            m = _HTML_TAG_RE.match(text, i)
            if m:
                spans.append((i, m.end(), 'html', '<'))
                i = m.end()
                continue
        if ch == '&':
            m = _HTML_ENTITY_RE.match(text, i)
            if m:
                spans.append((i, m.end(), 'html', '&'))
                i = m.end()
                continue
        if ch == '\\':
            opener = text[i:i + 2]
            if opener in ('\\(', '\\['):
                closer = '\\)' if opener == '\\(' else '\\]'
                close = text.find(closer, i + 2)
                if close < 0:
                    findings.append(_finding(
                        i, text, 'high', KIND_MATH_UNBALANCED,
                        'math opened with %s is never closed' % opener))
                    end = n
                else:
                    end = close + 2
                spans.append((i, end, 'math', opener))
                i = end
                continue
            nxt = text[i + 1:i + 2]
            if _LATEX_COMMAND_RE.match(text, i) or nxt in _LATEX_ESCAPES:
                end = _latex_run_end(text, i)
                spans.append((i, end, 'latex', text[i:end]))
                if include_info:
                    findings.append(_finding(
                        i, text, 'low', KIND_BARE_LATEX,
                        'LaTeX %r outside $...$ (the renderer re-wraps it, wrapping it is cleaner)'
                        % text[i:end][:24]))
                i = end
                continue
            findings.append(_finding(i, text, 'low', KIND_SYMBOL, 'stray backslash'))
            spans.append((i, i + 1, 'latex', '\\'))
            i += 1
            continue
        if ch == '$':
            if text.startswith('$$', i):
                close = text.find('$$', i + 2)
                if close < 0:
                    findings.append(_finding(
                        i, text, 'high', KIND_MATH_UNBALANCED,
                        'unclosed $$ — the field has %d $ sign(s) in total, so one is missing or '
                        'extra (the raw formula shows as text)' % text.count('$')))
                    end = n
                else:
                    end = close + 2
                spans.append((i, end, 'math', '$$'))
                i = end
                continue
            close = _inline_dollar_close(text, i)
            if close < 0:
                findings.append(_finding(
                    i, text, 'high', KIND_MATH_UNBALANCED,
                    'unclosed $ — the field has %d $ sign(s) in total, so one is missing or extra '
                    '(the raw formula shows as text)' % text.count('$')))
            else:
                spans.append((i, close + 1, 'math', '$'))
                i = close + 1
                continue
            spans.append((i, i + 1, 'math', '$'))
            i += 1
            continue
        i += 1
    return spans, findings


def _scan(text: str, include_info: bool = False):
    """``(region per index, findings)``; a region is ``None``/``'math'``/``'latex'``/``'html'``."""
    spans, findings = _scan_spans(text, include_info)
    regions: List[Optional[str]] = [None] * len(text)
    for start, end, kind, _opener in spans:
        for k in range(start, end):
            regions[k] = kind
    return regions, findings


def _classify_bangla(text: str, i: int) -> Optional[Finding]:
    """Report the Bangla-specific junk patterns: stranded / doubled dependent signs.

    ``া``/``ি``/``্`` … cannot start a word and — apart from the legacy ``ো``/``ৌ``
    decomposition (``ে``+``া``) that older data legitimately contains — cannot stand next to
    another vowel sign, so ``াকাশ`` or ``িকছু`` is a stray character, not a real word.
    """
    code = ord(text[i])
    if code not in _BANGLA_SIGNS:
        return None
    if i and text[i - 1:i + 1] in _BANGLA_COMPOSED_OK:
        return None
    j = i - 1
    while j >= 0 and text[j] in '\u200C\u200D':      # skip ZWNJ/ZWJ while looking back
        j -= 1
    if j >= 0 and text[j] == '>':                    # look past an inline tag such as <b>
        lt = text.rfind('<', max(0, j - 60), j)
        if lt >= 0:
            j = lt - 1
    prev = text[j] if j >= 0 else ''
    prev_code = ord(prev) if prev else 0
    prev_is_bangla = bool(prev) and (bool(_BANGLA_LETTER_RE.match(prev))
                                     or prev_code in _BANGLA_SIGNS)
    if prev_code in _BANGLA_VOWEL_SIGNS and code in _BANGLA_VOWEL_SIGNS:
        return _finding(i, text, 'medium', KIND_DOUBLE_SIGN,
                        'two Bangla vowel signs in a row (%s%s) — one of them is extra'
                        % (prev, text[i]))
    if prev_code == _BANGLA_HASANTA and code == _BANGLA_HASANTA:
        return _finding(i, text, 'medium', KIND_DOUBLE_SIGN,
                        'two conjunct signs (্) in a row — one of them is extra')
    if not prev_is_bangla:
        return _finding(i, text, 'medium', KIND_DANGLING,
                        'Bangla sign %s with no letter in front of it — stray character'
                        % text[i])
    if code == _BANGLA_HASANTA:
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if not (nxt and (_BANGLA_LETTER_RE.match(nxt) or nxt in '\u09CD\u200C\u200D')):
            return _finding(i, text, 'low', KIND_DANGLING,
                            'conjunct sign (্) with no letter after it — check it is intended')
    return None


def _classify(text: str, i: int, region: Optional[str]) -> Optional[Finding]:
    """Classify one character: a :class:`Finding` when it looks like junk, else ``None``."""
    ch = text[i]
    code = ord(ch)
    category = unicodedata.category(ch)

    if region in ('math', 'latex'):
        # Inside a formula anything the author typed is legitimate; only the code points that
        # make KaTeX fail are reported, and they are never auto-removed.
        if code == 0xFFFD:
            return _finding(i, text, 'high', KIND_MATH_JUNK,
                            'U+FFFD inside math breaks KaTeX')
        if category in ('Cc', 'Cf', 'Cn', 'Co', 'Cs') and ch not in '\t\n\r':
            return _finding(i, text, 'high', KIND_MATH_JUNK,
                            '%s inside math breaks KaTeX' % _char_name(ch).lower())
        if category == 'So' and _is_emoji(code):
            return _finding(i, text, 'medium', KIND_MATH_JUNK, 'emoji inside a formula')
        return None

    if region == 'html':
        # Markup (`<br> <sub>`, `&times;`) belongs to the record — the exporter shields it too.
        return None

    if code == 0xFFFD:
        return _finding(i, text, 'high', KIND_BROKEN,
                        'U+FFFD REPLACEMENT CHARACTER — a character was lost here, fix the word')
    if category == 'Cc':
        if ch in '\t\n\r':
            return None
        return _finding(i, text, 'high', KIND_BROKEN, 'control character')
    if category in ('Cn', 'Co', 'Cs'):
        return _finding(i, text, 'high', KIND_BROKEN, _char_name(ch).lower())
    if category == 'Cf':
        if code == 0x200C:
            return _finding(i, text, 'low', KIND_INVISIBLE,
                            'zero-width non-joiner (ZWNJ) — verify it is intentional')
        return _finding(i, text, 'medium', KIND_INVISIBLE,
                        'zero-width / invisible character — remove it')
    if category == 'Zs' and code != 0x20:
        return _finding(i, text, 'low', KIND_SPACE,
                        'non-breaking / typographic space — replace it with a normal space')
    if category in ('Zl', 'Zp'):
        return _finding(i, text, 'medium', KIND_SPACE, 'line / paragraph separator in the text')
    if _BANGLA_MIN <= code <= _BANGLA_MAX:
        return _classify_bangla(text, i)
    if _in_allowed_range(code) or ch in ALLOWED_EXTRA:
        return None
    if category in ('Lu', 'Ll', 'Lt', 'Lm', 'Lo'):
        latin = _lookalike(ch)
        if latin:
            return _finding(i, text, 'high', KIND_LOOKALIKE,
                            '%s imitates the Latin letter %r — pasted from another script'
                            % (_char_name(ch).title(), latin))
        return _finding(i, text, 'medium', KIND_FOREIGN,
                        'unexpected %s-script letter in Bangla/English text' % _script_name(ch))
    if category in ('Mn', 'Mc', 'Me'):
        return _finding(i, text, 'medium', KIND_FOREIGN,
                        'combining mark from another script (%s)' % _char_name(ch).title())
    if category in ('Nd', 'Nl', 'No'):
        latin = _lookalike(ch)
        if latin:
            return _finding(i, text, 'high', KIND_LOOKALIKE,
                            '%s imitates the digit %r — pasted from another script'
                            % (_char_name(ch).title(), latin))
        return _finding(i, text, 'medium', KIND_FOREIGN,
                        'numeral from another script (%s)' % _char_name(ch).title())
    if category in ('Sc', 'Sm', 'Sk', 'So'):
        if _is_emoji(code):
            return _finding(i, text, 'medium', KIND_EMOJI,
                            'emoji / pictograph %r — remove it' % ch)
        folded = _lookalike(ch)
        if folded:
            return _finding(i, text, 'medium', KIND_LOOKALIKE,
                            '%s imitates %r — use the plain character instead'
                            % (_char_name(ch).title(), folded))
        return _finding(i, text, 'medium', KIND_SYMBOL,
                        'unusual symbol (%s)' % _char_name(ch).title())
    return _finding(i, text, 'low', KIND_SYMBOL, 'unusual character in this text')


# -------------------------------------------------------------- scanning ----
def scan_text(text, include_info: bool = False) -> List[Finding]:
    """Report every suspicious character of one field, in text order.

    Math (``$…$``, ``$$…$$``, ``\\(…\\)``, ``\\[…\\]``) and its LaTeX commands, HTML tags and
    entities, Bangla, English and the generally used symbols are never reported. Set
    ``include_info=True`` to also get the informational findings (:data:`INFO_KINDS`, e.g.
    bare LaTeX outside ``$...$``).
    """
    source = str(text if text is not None else '')
    if not source:
        return []
    regions, findings = _scan(source, include_info)
    ascii_only = source.isascii()
    for i, ch in enumerate(source):
        if ascii_only and (' ' <= ch <= '~' or ch in '\t\n\r'):
            continue
        found = _classify(source, i, regions[i])
        if found is not None:
            findings.append(found)
    findings.sort(key=lambda f: f.index)
    return findings


def scan_row(row, fields: Optional[Sequence[str]] = None,
             include_info: bool = False) -> Dict[str, List[Finding]]:
    """Scan every text field of a question record; only fields with findings are returned."""
    found: Dict[str, List[Finding]] = {}
    for field in (fields if fields is not None else SCAN_FIELDS):
        if row is None or not hasattr(row, 'get'):
            break
        items = scan_text(row.get(field), include_info=include_info)
        if items:
            found[field] = items
    return found


def summarize(findings, limit: int = 4) -> str:
    """One-line summary of a field's findings, e.g.

    ``U+200B ZERO WIDTH SPACE ×3 @12,41,77 (invisible)``.
    """
    groups: Dict[Tuple[int, str, str], List[int]] = {}
    for item in findings or ():
        groups.setdefault((item.code, item.name, item.kind), []).append(item.index)
    ordered = sorted(groups.items(), key=lambda kv: kv[1][0])
    parts: List[str] = []
    for (code, name, kind), offsets in ordered[:limit]:
        shown = ','.join(str(o) for o in offsets[:4]) + (',…' if len(offsets) > 4 else '')
        count = ' ×%d' % len(offsets) if len(offsets) > 1 else ''
        parts.append('U+%04X %s%s @%s (%s)' % (code, name, count, shown, kind))
    if len(ordered) > limit:
        parts.append('+%d more kind(s)' % (len(ordered) - limit))
    return '; '.join(parts)


def severity_counts(findings) -> Dict[str, int]:
    """``{'high': n, 'medium': n, 'low': n}`` — only the severities that occur."""
    counts: Dict[str, int] = {}
    for item in findings or ():
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return counts


# ------------------------------------------------------------- cleanup -----
def strip_junk(text) -> Tuple[str, List[Finding]]:
    """Delete the code points that are broken beyond doubt (never inside math/HTML).

    Returns ``(cleaned_text, removed_findings)``. Only :data:`AUTO_STRIP_CODES` plus control,
    private-use, surrogate and unassigned code points are deleted — ZWNJ, unusual spaces,
    emoji and mixed-script letters are only reported by :func:`scan_text`, so a human/AI
    decides what the word should become. ``\\t``/``\\n``/``\\r`` are always kept, and a
    formula (``$…$``, ``$$…$$``, ``\\(…\\)``, ``\\[…\\]``, ``\\cmd{…}``) or HTML markup is
    never modified at all.
    """
    source = str(text if text is not None else '')
    if not source:
        return source, []
    if source.isascii() and not _CONTROL_RE.search(source):
        return source, []                 # plain ASCII holds nothing removable
    regions, _findings = _scan(source)
    kept: List[str] = []
    removed: List[Finding] = []
    for i, ch in enumerate(source):
        if regions[i] in ('math', 'latex', 'html'):
            kept.append(ch)               # a formula / tag must stay byte-identical
            continue
        code = ord(ch)
        if code in AUTO_STRIP_CODES:
            removed.append(_classify(source, i, None)
                           or _finding(i, source, 'high', KIND_BROKEN, 'removed'))
            continue
        if ch in '\t\n\r':
            kept.append(ch)
            continue
        if code < 0x20 or 0x7E < code < 0xA0 or unicodedata.category(ch) in ('Cn', 'Co', 'Cs'):
            removed.append(_classify(source, i, None)
                           or _finding(i, source, 'high', KIND_BROKEN, 'removed'))
            continue
        kept.append(ch)
    return ''.join(kept), removed


def formula_signature(text):
    """Fingerprint of the formulas in a field.

    Returns ``(latex_commands, delimiter_chars, digits_in_math)`` where ``delimiter_chars`` is
    ``(display $$, inline $, \\(, \\[)`` counted as characters — enough to notice that an edit
    dropped, mangled or renumbered a formula.
    """
    source = str(text if text is not None else '')
    if not source:
        return ((), (0, 0, 0, 0), '')
    spans, _info = _scan_spans(source)
    commands: Counter = Counter()
    digits: List[str] = []
    counts = {'$$': 0, '$': 0, '\\(': 0, '\\[': 0}
    closers = {'$$': '$$', '$': '$', '\\(': '\\)', '\\[': '\\]'}
    for start, end, kind, opener in spans:
        body = source[start:end]
        if kind == 'math':
            closer = closers[opener]
            closed = end - start > len(opener) and source[end - len(closer):end] == closer
            counts[opener] += len(opener) + (len(closer) if closed else 0)
            commands.update(_LATEX_COMMAND_RE.findall(body))
        elif kind == 'latex':
            m = _LATEX_COMMAND_RE.match(source, start)
            if m:
                commands[m.group(0)] += 1
        else:
            continue
        digits.extend(c for c in body if c.isdigit())
    return (tuple(sorted(commands.items())),
            (counts['$$'], counts['$'], counts['\\('], counts['\\[']),
            ''.join(digits))


def formula_diff_reasons(orig, new) -> List[str]:
    """Reasons an edit damaged a formula — ``[]`` when every formula survived.

    Only *losses* are reported: a missing LaTeX command, fewer math delimiters than the
    original, digits inside math that changed, or inline math left unbalanced. Wrapping bare
    LaTeX in ``$...$`` (what the render pipeline does anyway) is not a loss.
    """
    reasons: List[str] = []
    o_cmd, o_del, o_digits = formula_signature(orig)
    n_cmd, n_del, n_digits = formula_signature(new)
    n_map = dict(n_cmd)
    lost = sorted(cmd for cmd, count in dict(o_cmd).items() if n_map.get(cmd, 0) < count)
    if lost:
        reasons.append('LaTeX command(s) lost: %s' % ', '.join(lost))
    for label, before, after in (('$$', o_del[0], n_del[0]), ('$', o_del[1], n_del[1]),
                                 (r'\(', o_del[2], n_del[2]), (r'\[', o_del[3], n_del[3])):
        if after < before:
            reasons.append('math delimiter %s reduced (%d -> %d)' % (label, before, after))
    if o_digits and n_digits != o_digits:
        reasons.append('digits inside math changed (%s -> %s)' % (o_digits[:20], n_digits[:20]))
    if n_del[1] % 2 and not o_del[1] % 2:
        reasons.append('inline $ math left unbalanced')
    return reasons


def sanitize_fields(row, cleaned, fields=None):
    """Post-check an AI reply before it becomes a pending update request.

    Two safety nets: code points that are broken beyond doubt are deleted even when the AI
    kept them (:func:`strip_junk`), and a field whose formula the edit damaged falls back to
    the original text instead of storing a broken formula (:func:`formula_diff_reasons`).

    ``cleaned`` is updated in place. Returns ``(notes, stats)`` with ``stats['removed']``
    (code points deleted) and ``stats['reverted']`` (fields restored to the original).
    """
    notes: List[str] = []
    stats = {'removed': 0, 'reverted': []}
    for field in (fields if fields is not None else list(cleaned.keys())):
        if field not in cleaned:
            continue
        value = str(cleaned.get(field) or '')
        if not value:
            continue
        original = str(row.get(field) or '') if hasattr(row, 'get') else ''
        fixed, removed = strip_junk(value)
        if removed:
            stats['removed'] += len(removed)
            notes.append('%s: removed %s' % (field, summarize(removed)))
        reasons = formula_diff_reasons(original, fixed)
        if reasons and original.strip():
            notes.append('%s: AI edit reverted — %s' % (field, '; '.join(reasons)))
            stats['reverted'].append(field)
            cleaned[field] = original
        else:
            cleaned[field] = fixed
    return notes, stats


# ------------------------------------------------------------ fixing junk ---
#: Findings that are *replaced* (not deleted) when accepted, keyed by Unicode category: a special
#: space becomes a normal space and a line/paragraph separator a newline, so two words never get
#: glued together by an accepted finding.
_FIX_REPLACEMENTS = {'Zs': ' ', 'Zl': '\n', 'Zp': '\n'}


def finding_replacement(item: Finding) -> str:
    """What an accepted finding becomes: ``''`` (delete it) or the plain character.

    Unusual spaces are the only findings that are replaced instead of deleted — deleting a
    non-breaking space between two words would glue them together, which is a word-level change
    this character pass must never make. Everything else (zero-width code point, U+FFFD, a
    look-alike letter pasted from another script) is taken out and the rest of the text is copied
    byte-for-byte.
    """
    return _FIX_REPLACEMENTS.get(unicodedata.category(item.char), '')


def fix_findings(text, findings):
    """Apply the accepted findings to one field. Returns ``(cleaned, applied)``.

    Only a character that really sits at its recorded offset is touched, so a stale or foreign
    finding can never corrupt the text. No word, no spacing and no sentence is ever changed.
    """
    source = str(text if text is not None else '')
    picked: Dict[int, Finding] = {}
    for item in findings or ():
        if 0 <= item.index < len(source) and source[item.index] == item.char:
            picked[item.index] = item
    if not picked:
        return source, []
    kept: List[str] = []
    for i, ch in enumerate(source):
        item = picked.get(i)
        kept.append(ch if item is None else finding_replacement(item))
    return ''.join(kept), [picked[i] for i in sorted(picked)]


def remove_indices(text, indices) -> Tuple[str, int]:
    """Delete the characters at ``indices`` — ``(cleaned, removed_count)`` (review-markup helper)."""
    source = str(text if text is not None else '')
    drop = {i for i in indices or () if 0 <= i < len(source)}
    if not drop:
        return source, 0
    return ''.join(ch for i, ch in enumerate(source) if i not in drop), len(drop)


def sure_removals(findings) -> List[Finding]:
    """Findings that are broken beyond doubt (:data:`AUTO_STRIP_CODES`), so no AI opinion is needed."""
    return [item for item in findings or ()
            if item.kind == KIND_BROKEN or item.code in AUTO_STRIP_CODES]


def removable(findings) -> List[Finding]:
    """Findings that may be taken out of the text (the :data:`REPORT_ONLY_KINDS` are left alone).

    An unbalanced ``$`` is reported but never removed: the stray sign may as well be a *missing*
    one, so deleting it could damage a formula that renders — only the admin decides that case.
    """
    return [item for item in findings or () if item.kind not in REPORT_ONLY_KINDS]



# -------------------------------------------------------------- AI prompt ---
PROMPT_RULE = (
    "Task: mark ONLY the unwanted extra characters of this Bangladesh national-curriculum question "
    "(Bangla medium). Do NOT correct spelling, grammar, wording, punctuation or word spacing — "
    "every word and every sentence must stay exactly as it is."
)
REMOVE_RULE = (
    "UNWANTED (list its number): invisible / zero-width code points (U+200B, U+200C, U+200D, "
    "U+FEFF, U+00AD, U+202A-U+202E), control characters, U+FFFD, private-use or unassigned code "
    "points, emoji and pictographs, box-drawing / dingbat symbols, letters or digits pasted from "
    "another script that imitate a Bangla/English character (Cyrillic а е о с р х, full-width "
    "ＡＢＣ, mathematical 𝐀 𝟏), a non-breaking or typographic space, a Bangla sign written twice in "
    "a row, a Bangla sign with no letter to attach to, and symbols no school question uses."
)
KEEP_RULE = (
    "KEEP (never list them): the punctuation that carries the meaning of the sentence — ? ! . , ; : "
    "\" ' - ( ) [ ] { } / % & * + = < > — Bangla and English letters/digits, transliteration "
    "letters (ā ī ū ṛ ṭ ḍ ś ṣ ḥ ñ), Greek letters, school symbols (× ÷ ± ≤ ≥ ≠ ≈ ∞ ∴ ∵ ∠ ° √ → ← • ৳ ₹ "
    "½ …) and the record's HTML markup (<br> <b> <i> <sub> <sup>, entities such as &times;)."
)
MATH_RULE = (
    "LaTeX / KaTeX / MathJax and HTML are NOT special characters: never list or change anything "
    "inside $...$, $$...$$, \\(...\\), \\[...\\], a \\command or a tag — the delimiters and every "
    "number inside a formula are correct content."
)
ANSWER_RULE = (
    "Answer with ONLY valid JSON, no markdown: {\"remove\":{\"<field>\":[<numbers>]}} — for example "
    "{\"remove\":{\"question\":[1,3]}}. A candidate you do not list is kept; answer {} when none of "
    "them is unwanted. Never return the text of a field — only these numbers."
)


def context_window(text, index: int, width: int = 24) -> str:
    """Readable window around one character, for the Home AI prompt.

    The character itself shows as ``[HERE]`` and every invisible code point of the window is
    spelled out (``<U+200B>``) — otherwise a zero-width space would be invisible to the AI and to
    the admin reading the prompt.
    """
    source = str(text if text is not None else '')
    start = max(0, index - width)
    end = min(len(source), index + width + 1)
    return '%s%s[HERE]%s%s' % (
        '…' if start > 0 else '',
        _visible_text(source[start:index]),
        _visible_text(source[index + 1:end]),
        '…' if end < len(source) else '',
    )


def _visible_text(value: str) -> str:
    """Text with the invisible / non-printing characters written as ``<U+XXXX>``."""
    out: List[str] = []
    for ch in value:
        code = ord(ch)
        if ch in '\t\n\r':
            out.append(' ')
        elif code < 0x20 or code in AUTO_STRIP_CODES or unicodedata.category(ch) in ('Cf', 'Co', 'Cs'):
            out.append('<U+%04X>' % code)
        else:
            out.append(ch)
    return ''.join(out)


def flatten_candidates(findings) -> List[Tuple[str, Finding]]:
    """Flat ``[(field, finding), …]`` list of a :func:`scan_row` map (field order, text order)."""
    ordered: List[Tuple[str, Finding]] = []
    for field, items in (findings or {}).items():
        for item in items or ():
            ordered.append((field, item))
    return ordered


def candidate_lines(ordered, row, limit: int = 60) -> List[str]:
    """The numbered candidate lines of the Home AI prompt, e.g.

    ``  1. question @41 U+200B ZERO WIDTH SPACE (invisible) — "…পদার্থ[HERE]বিজ্ঞান…"``
    """
    lines: List[str] = []
    for number, (field, item) in enumerate(ordered[:limit], start=1):
        text = row.get(field) if hasattr(row, 'get') else ''
        lines.append('  %d. %s @%d %s %s (%s) — "%s"'
                     % (number, field, item.index, item.code_label, item.name, item.kind,
                        context_window(text, item.index)))
    if len(ordered) > limit:
        lines.append('  … and %d more code point(s) of the same kinds.' % (len(ordered) - limit))
    return lines


def build_prompt_block(row, findings, limit: int = 60):
    """Prompt lines for the Home AI unwanted-character check.

    ``findings`` is a :func:`scan_row` map (only the fields and code points to be judged — the
    caller drops the ones that are broken beyond doubt). Returns ``(lines, ordered)`` where
    ``ordered`` is :func:`flatten_candidates`, so candidate *n* of the numbering is
    ``ordered[n - 1]``; that is how the AI's answer is mapped back to a real character.
    """
    ordered = flatten_candidates(findings)
    if not ordered:
        return [], ordered
    lines = ['CANDIDATE CODE POINTS (numbered — answer these numbers):']
    lines.extend(candidate_lines(ordered, row, limit))
    lines.append(ANSWER_RULE)
    lines.append(REMOVE_RULE)
    lines.append(KEEP_RULE)
    lines.append(MATH_RULE)
    return lines, ordered








