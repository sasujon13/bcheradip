"""
LaTeX source normalization for PDF/HTML export (mirrors fcheradip question-katex-render.ts).
KaTeX HTML is produced in Playwright via auto-render before page.pdf().

Bundled under ``cheradip/static/vendor/katex/<version>/`` so PDF export works on Linux
servers without outbound CDN access (jsDelivr).
"""
from __future__ import annotations

import re
from pathlib import Path

_ZW_CHARS_RE = re.compile(r'[\u200B-\u200D\uFEFF]')
_BOXED_TAIL_RE = re.compile(
    r'\$\$(\s*\\boxed\{(?:[^{}]|\{[^{}]*\})*\})\s*\$(?!\$)',
    re.DOTALL,
)
_BARE_LATEX_COMMAND_RE = re.compile(
    r'\\(?:(?:frac|dfrac|tfrac|sqrt|begin|end|mathrm|text|operatorname|mathbf|mathit|'
    r'mathbb|mathcal|boxed|therefore|because|times|cdot|div|sum|prod|int|iint|lim|'
    r'log|ln|sin|cos|tan|theta|alpha|beta|gamma|delta|lambda|mu|pi|sigma|omega|'
    r'infty|le|ge|neq|approx|rightarrow|left|right|overline|underline|vec|hat|bar|'
    r'unit|cancel)\b|[%*])'
)
_BENGALI_RE = re.compile(r'[\u0980-\u09ff]')
_ENGLISH_PROSE_BOUNDARY_RE = re.compile(
    r'\s+(?:where|when|which|given|find|calculate|hence|in which|for which|so that)\b',
    re.IGNORECASE,
)
_FORMAT_SHIELD_RE = re.compile(
    r'\$\$[\s\S]*?\$\$|\$(?!\$)[^$\n]*?\$|\\\[[\s\S]*?\\\]|'
    r'\\\([\s\S]*?\\\)|<[^>]*>'
)
_CALCULATION_LABEL_AFTER_BOUNDARY_RE = re.compile(
    r'(?:^|[।.!?\n\r,:])\s*'
    r'([A-Za-z\u0980-\u09ff][A-Za-z\u0980-\u09ff\u200c\u200d]*'
    r'(?:[ \t]+(?:[A-Za-z\u0980-\u09ff][A-Za-z\u0980-\u09ff\u200c\u200d]*|'
    r'\([^()\r\n]{1,50}\))){0,5})[ \t]*=',
    re.IGNORECASE,
)


def _is_prose_boundary_at(source: str, index: int) -> bool:
    ch = source[index]
    if _BENGALI_RE.match(ch) or ch in '।<\r\n':
        return True
    return bool(ch.isspace() and _ENGLISH_PROSE_BOUNDARY_RE.match(source[index:]))


def _is_prose_after_math_close(source: str, index: int) -> bool:
    """True when the character right after a closing math delimiter at ``index`` starts prose rather
    than more math. Used to distinguish a well-formed inline ``$...$`` (which must NOT be merged with
    a later ``$$`` block) from an unbalanced single-``$`` opener (a legacy import-quirk to repair)."""
    if index + 1 >= len(source):
        return True
    ch = source[index + 1]
    if ch == '$' or ch == '\\':
        return False
    if ch.isspace() or _BENGALI_RE.match(ch) or ch in '।,;:!?()[]“”"\'<>-\r\n':
        return True
    return False


def normalize_question_calculation_layout(text: str) -> str:
    """Restore sentence spacing and continuation lines in flattened calculations."""
    if not text:
        return ''
    shields: list[str] = []

    def shield(match: re.Match) -> str:
        token = f'\ue000{len(shields)}\ue001'
        shields.append(match.group(0))
        return token

    source = _FORMAT_SHIELD_RE.sub(shield, str(text))
    source = re.sub(r'।(?![\s<]|$)', '। ', source)

    labels: list[str] = []
    seen: set[str] = set()
    for match in _CALCULATION_LABEL_AFTER_BOUNDARY_RE.finditer(source):
        label = re.sub(r'[ \t]+', ' ', match.group(1)).strip()
        folded = label.casefold()
        if label and folded not in seen:
            labels.append(label)
            seen.add(folded)

    changed_calculation = False
    for label in labels:
        label_re = re.compile(rf'({re.escape(label)})[ \t]*=', re.IGNORECASE)
        occurrences = list(label_re.finditer(source))
        if len(occurrences) < 2:
            continue
        roman_prefixed = [
            match for match in occurrences
            if re.search(
                r'(?:^|[^A-Za-z])(?:iii|ii|i)\.?\s*$',
                source[max(0, match.start() - 10):match.start()],
                re.I,
            )
        ]
        if len(roman_prefixed) >= 2:
            continue
        occurrence = 0

        def replace_label(match: re.Match) -> str:
            nonlocal occurrence, changed_calculation
            occurrence += 1
            changed_calculation = True
            if occurrence == 1:
                needs_break = (
                    match.start() > 0
                    and source[match.start() - 1] != '\n'
                    and bool(source[:match.start()].strip())
                )
                return ('\n' if needs_break else '') + match.group(1) + ' ='
            return '\n='

        source = label_re.sub(replace_label, source)

    if changed_calculation:
        source = re.sub(
            r'([0-9A-Za-z\u09f9°%)}\]])[ \t]*(সুতরাং|অতএব|Hence\b|Therefore\b)',
            r'\1\n\2',
            source,
            flags=re.IGNORECASE,
        )
    source = re.sub(r'[ \t]+\n', '\n', source)

    def restore(match: re.Match) -> str:
        index = int(match.group(1))
        return shields[index] if index < len(shields) else ''

    return re.sub(r'\ue000(\d+)\ue001', restore, source)

# KaTeX 0.16.x — keep in sync with fcheradip package.json / static vendor folder
EXPORT_KATEX_VERSION = '0.16.11'
_EXPORT_KATEX_STATIC_DIR = (
    Path(__file__).resolve().parent / 'static' / 'vendor' / 'katex' / EXPORT_KATEX_VERSION
)


def katex_static_dir() -> Path:
    return _EXPORT_KATEX_STATIC_DIR


def katex_static_assets_available() -> bool:
    d = _EXPORT_KATEX_STATIC_DIR
    return (
        (d / 'katex.min.js').is_file()
        and (d / 'katex.min.css').is_file()
        and (d / 'contrib' / 'auto-render.min.js').is_file()
    )


def _find_boxed_group_end(s: str, from_: int) -> int:
    rest = s[from_:]
    stripped = rest.lstrip()
    if not stripped.startswith('\\boxed{'):
        return -1
    i = from_ + (len(rest) - len(stripped)) + 7
    depth = 1
    while i < len(s) and depth > 0:
        ch = s[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        i += 1
    return i if depth == 0 else -1


def _repair_legacy_latex_tokens(source: str) -> str:
    if not re.search(r'\\(?:[A-Za-z]+|[%*])', source):
        return source
    source = re.sub(r'\*\s*\{', '_{', source)
    source = re.sub(r'\\+\*', r'\\times ', source)
    source = re.sub(r'\\+%', r'\\%', source)
    return re.sub(
        r'\\mathrm\s*\{\s*\\~\s*([^{}]+)\}',
        r'\\mathrm{\1}',
        source,
    )


def _repair_single_open_double_close_blocks(source: str) -> str:
    """Repair ``$...$...$$prose`` with stray internal dollars as one display formula."""
    out: list[str] = []
    cursor = 0
    while cursor < len(source):
        open_ = source.find('$', cursor)
        if open_ < 0:
            out.append(source[cursor:])
            break
        if (open_ > 0 and source[open_ - 1] in '\\$') or (
            open_ + 1 < len(source) and source[open_ + 1] == '$'
        ):
            out.append(source[cursor:open_ + 1])
            cursor = open_ + 1
            continue
        # If the first $ is already closed as a well-formed inline $...$ (its closing $ is followed by
        # prose), do NOT merge it with any later $$ block — that would swallow the prose and the next
        # formula into one display expression (e.g. `$F=...$ এবং $$E=...$$`).
        quick_close = _next_unescaped_inline_dollar(source, open_ + 1)
        if quick_close >= 0 and _is_prose_after_math_close(source, quick_close):
            out.append(source[cursor:open_ + 1])
            cursor = open_ + 1
            continue
        terminal = source.find('$$', open_ + 1)
        repaired = False
        while terminal >= 0:
            body = source[open_ + 1:terminal]
            after = source[terminal + 2:terminal + 3]
            if (
                '$' in body
                and _BARE_LATEX_COMMAND_RE.search(body)
                and (not after or _is_prose_boundary_at(source, terminal + 2))
            ):
                clean_body = body.replace('$', '')
                clean_body = re.sub(
                    r'^\s*(i{1,3}|iv)\.\s*',
                    lambda m: r'\text{' + m.group(1) + '. } ',
                    clean_body,
                    flags=re.I,
                )
                clean_body = re.sub(
                    r'\s+(i{2,3}|iv)\.\s*',
                    lambda m: r' \quad \text{' + m.group(1) + '. } ',
                    clean_body,
                    flags=re.I,
                )
                out.extend((source[cursor:open_], '$$', clean_body.strip(), '$$'))
                cursor = terminal + 2
                repaired = True
                break
            terminal = source.find('$$', terminal + 2)
        if not repaired:
            out.append(source[cursor:open_ + 1])
            cursor = open_ + 1
    return ''.join(out)


def _repair_mixed_dollar_blocks(source: str) -> str:
    """Convert malformed ``$...$$...$$...$`` into one display expression."""
    out: list[str] = []
    i = 0
    while i < len(source):
        is_single_open = (
            source[i] == '$'
            and (i == 0 or source[i - 1] not in '$\\')
            and (i + 1 >= len(source) or source[i + 1] != '$')
        )
        if not is_single_open:
            out.append(source[i])
            i += 1
            continue
        close = -1
        j = i + 1
        while j < len(source):
            if source[j] != '$' or source[j - 1] == '\\':
                j += 1
                continue
            if j + 1 < len(source) and source[j + 1] == '$':
                j += 2
                continue
            if source[j - 1] == '$':
                j += 1
                continue
            close = j
            break
        if close < 0:
            out.append(source[i:])
            break
        inner = source[i + 1:close]
        if '$$' in inner and _BARE_LATEX_COMMAND_RE.search(inner):
            out.append('$$' + inner.replace('$$', r'\\') + '$$')
        else:
            out.append(source[i:close + 1])
        i = close + 1
    return ''.join(out)


def _find_unterminated_display_end(source: str, from_: int) -> int:
    env = re.search(r'\\begin\s*\{([^{}]+)\}', source[from_:])
    if env:
        begin_at = from_ + env.start()
        end_token = rf'\end{{{env.group(1)}}}'
        env_end = source.find(end_token, begin_at + len(env.group(0)))
        if env_end >= 0:
            return env_end + len(end_token)
    depth = 0
    for i in range(from_, len(source)):
        ch = source[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth = max(0, depth - 1)
        if depth == 0 and _is_prose_boundary_at(source, i):
            return i
    return len(source)


def _close_unterminated_display_math(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        open_ = s.find('$$', i)
        if open_ < 0:
            out.append(s[i:])
            break
        out.append(s[i:open_])
        close = s.find('$$', open_ + 2)
        if close >= 0:
            out.append(s[open_: close + 2])
            i = close + 2
            continue
        content_start = open_ + 2
        boxed_end = _find_boxed_group_end(s, content_start)
        if boxed_end > content_start:
            out.append('$$')
            out.append(s[content_start:boxed_end])
            out.append('$$')
            i = boxed_end
            continue
        inferred_end = _find_unterminated_display_end(s, content_start)
        out.extend(('$$', s[content_start:inferred_end], '$$'))
        i = inferred_end
    return ''.join(out)


def _bare_latex_end(segment: str, from_: int) -> int:
    env = re.match(r'\\begin\s*\{([^{}]+)\}', segment[from_:])
    if env:
        token = rf'\end{{{env.group(1)}}}'
        end = segment.find(token, from_ + len(env.group(0)))
        if end >= 0:
            return end + len(token)
    depth = 0
    for i in range(from_, len(segment)):
        ch = segment[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth = max(0, depth - 1)
        if depth == 0 and _is_prose_boundary_at(segment, i):
            return i
    return len(segment)


def _wrap_bare_latex_in_plain_segment(segment: str) -> str:
    out: list[str] = []
    cursor = 0
    while cursor < len(segment):
        match = _BARE_LATEX_COMMAND_RE.search(segment, cursor)
        if not match:
            out.append(segment[cursor:])
            break
        before = segment[:match.start()].lower()
        if before.rfind('<code') > before.rfind('</code>'):
            out.append(segment[cursor:match.end()])
            cursor = match.end()
            continue
        start = match.start()
        prefix = re.search(
            r'([A-Za-z][A-Za-z0-9_]*\s*=\s*[A-Za-z0-9_.()+\-*/ ]*)$',
            segment[:start],
        )
        if prefix:
            start -= len(prefix.group(1))
        end = _bare_latex_end(segment, match.start())
        while end > start and segment[end - 1].isspace():
            end -= 1
        if end <= match.start():
            out.append(segment[cursor:match.end()])
            cursor = match.end()
            continue
        formula = segment[start:end]
        out.append(segment[cursor:start])
        standalone_calculation = bool(
            start == 0
            and re.match(r'^[A-Za-z][A-Za-z0-9_]*\s*=', formula)
            and end < len(segment)
        )
        display = bool(re.search(r'\\begin\s*\{', formula)) or standalone_calculation
        out.append(('$$' if display else '$') + formula)
        out.append('$$' if display else '$')
        cursor = end
    return ''.join(out)


def _next_unescaped_inline_dollar(source: str, from_: int) -> int:
    p = from_
    while p < len(source):
        if source[p] != '$' or (p > 0 and source[p - 1] == '\\'):
            p += 1
            continue
        if p + 1 < len(source) and source[p + 1] == '$':
            p += 2
            continue
        return p
    return -1


def _backslash_math_block_bounds(source: str, i: int):
    """If ``source[i:]`` opens a backslash math delimiter ``\\(...\\)`` or ``\\[...\\]`` with a
    matching close, return ``(start, end)`` covering the whole block inclusive of delimiters; else
    None. These are real math delimiters (``iter_question_latex_segments`` recognizes them), so their
    bodies must NOT be re-wrapped as bare LaTeX below — re-wrapping injected stray ``$`` and corrupted
    the encoded Word math / leaked raw ``$`` into running text."""
    if source[i:i + 2] == '\\(':
        close = source.find('\\)', i + 2)
        if close < 0:
            return None
        return (i, close + 2)
    if source[i:i + 2] == '\\[':
        close = source.find('\\]', i + 2)
        if close < 0:
            return None
        return (i, close + 2)
    return None



def _wrap_bare_latex_outside_delimiters(source: str) -> str:
    out: list[str] = []
    plain_start = 0
    i = 0
    while i < len(source):
        if source[i] == '\\' and (i == 0 or source[i - 1] != '\\'):
            block = _backslash_math_block_bounds(source, i)
            if block is not None:
                block_start, block_end = block
                wrapped_plain = _wrap_bare_latex_in_plain_segment(source[plain_start:i])
                out.append(wrapped_plain)
                if wrapped_plain.endswith('$'):
                    out.append('\n')
                out.append(source[block_start:block_end])
                i = block_end
                plain_start = i
                continue

        if source.startswith('$$', i):
            close = source.find('$$', i + 2)
            if close < 0:
                break
            wrapped_plain = _wrap_bare_latex_in_plain_segment(source[plain_start:i])
            out.append(wrapped_plain)
            if wrapped_plain.endswith('$'):
                out.append('\n')
            out.append(source[i:close + 2])
            i = close + 2
            plain_start = i
            continue
        if source[i] == '$' and (i == 0 or source[i - 1] != '\\'):
            close = _next_unescaped_inline_dollar(source, i + 1)
            if close < 0:
                break
            out.append(_wrap_bare_latex_in_plain_segment(source[plain_start:i]))
            out.append(source[i:close + 1])
            i = close + 1
            plain_start = i
            continue
        i += 1
    wrapped_tail = _wrap_bare_latex_in_plain_segment(source[plain_start:])
    if out and out[-1].endswith('$$') and wrapped_tail.startswith('$'):
        out.append('\n')
    out.append(wrapped_tail)
    return ''.join(out)


def _normalize_inline_math_tex(s: str) -> str:
    """Strip trailing ``\\\\`` inside ``$...$`` and tighten ``\\text { ... }`` spacing."""

    def repl(m: re.Match) -> str:
        inner = m.group(1)
        inner = re.sub(r'\\+$', '', inner).strip()
        inner = re.sub(
            r'\\(text|mathrm|operatorname|mathbf|mathit)\s*\{\s*',
            r'\\\1{',
            inner,
        )
        inner = re.sub(r'\s+\}', '}', inner)
        return f'${inner}$'

    return re.sub(r'\$([^$\n]+?)\$', repl, s)


def normalize_question_latex_source(text: str) -> str:
    """Same rules as Angular ``normalizeQuestionLatexSource`` before KaTeX."""
    if not text:
        return ''
    s = _ZW_CHARS_RE.sub('', normalize_question_calculation_layout(str(text)))
    s = _repair_legacy_latex_tokens(s)
    s = _repair_single_open_double_close_blocks(s)
    s = _repair_mixed_dollar_blocks(s)
    s = re.sub(r'\\+\s*\$\$', '\n$$', s)
    s = _BOXED_TAIL_RE.sub(r'$$\1$$', s)
    s = _normalize_inline_math_tex(s)
    s = _close_unterminated_display_math(s)
    return _wrap_bare_latex_outside_delimiters(s)


def iter_question_latex_segments(text: str):
    """Yield ``(kind, value, display_mode)`` after repairing imported question math."""
    source = normalize_question_latex_source(text)
    cursor = 0
    openers = (('$$', '$$', True), (r'\[', r'\]', True), (r'\(', r'\)', False), ('$', '$', False))
    while cursor < len(source):
        candidates = []
        for left, right, display in openers:
            pos = source.find(left, cursor)
            if pos >= 0:
                candidates.append((pos, -len(left), left, right, display))
        if not candidates:
            if cursor < len(source):
                yield ('text', source[cursor:], False)
            break
        pos, _priority, left, right, display = min(candidates)
        if pos > cursor:
            yield ('text', source[cursor:pos], False)
        end = source.find(right, pos + len(left))
        if end < 0:
            yield ('text', source[pos:], False)
            break
        yield ('math', source[pos + len(left):end], display)
        cursor = end + len(right)


def latex_to_readable_text(tex: str) -> str:
    """A non-raw fallback for DOCX hosts where the KaTeX image renderer is unavailable."""
    value = str(tex or '')
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r'\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}', r'(\1)/(\2)', value)
        value = re.sub(
            r'\\(?:text|mathrm|operatorname|mathbf|mathit|mathbb|mathcal)\s*\{([^{}]*)\}',
            r'\1',
            value,
        )
    replacements = {
        r'\times': '×', r'\cdot': '·', r'\div': '÷', r'\therefore': '∴',
        r'\because': '∵', r'\le': '≤', r'\ge': '≥', r'\neq': '≠',
        r'\approx': '≈', r'\rightarrow': '→', r'\infty': '∞', r'\\': ' ',
        '&': '',
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r'\\(?:begin|end)\s*\{[^{}]+\}', ' ', value)
    value = re.sub(r'\\(?:left|right)', '', value)
    value = re.sub(r'\^\{([^{}]+)\}', r'^\1', value)
    value = re.sub(r'_\{([^{}]+)\}', r'_\1', value)
    value = re.sub(r'\\([A-Za-z]+)', r'\1', value)
    value = value.replace('{', '').replace('}', '')
    return re.sub(r'\s+', ' ', value).strip()


# Legacy CDN fallback (dev machines with network but missing static bundle).
EXPORT_KATEX_CDN = f'https://cdn.jsdelivr.net/npm/katex@{EXPORT_KATEX_VERSION}/dist'

EXPORT_KATEX_HEAD_HTML = f"""
  <link rel="stylesheet" href="{EXPORT_KATEX_CDN}/katex.min.css" crossorigin="anonymous" />
"""

EXPORT_KATEX_PDF_CSS = """
    .katex { font-size: 1em; color: inherit; }
    .katex-display { display: block; margin: 0.35em 0; overflow-x: auto; overflow-y: hidden; text-align: left !important; }
    .katex-display > .katex { text-align: left !important; }
    .question-math-fallback-display { display: block; margin: 0.35em 0; text-align: left; white-space: pre-wrap; }
    .topic-question-line .katex-display { margin: 0.25em 0; }
"""

# Inline runner when assets are injected via page.add_style_tag / add_script_tag (local bundle).
EXPORT_KATEX_PDF_RUN_SCRIPT = r"""
(function(){
  function done(){ window.__katexPdfDone = true; }
  function replaceFailedDisplayMath(root){
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var nodes = [];
    var node;
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (!parent || parent.closest('.katex,script,style,code,pre')) continue;
      if (node.nodeValue && node.nodeValue.indexOf('$$') >= 0) nodes.push(node);
    }
    nodes.forEach(function(textNode){
      var source = textNode.nodeValue || '';
      var regex = /\$\$([\s\S]*?)\$\$/g;
      var match;
      var cursor = 0;
      var fragment = document.createDocumentFragment();
      var changed = false;
      while ((match = regex.exec(source))) {
        changed = true;
        if (match.index > cursor) fragment.appendChild(document.createTextNode(source.slice(cursor, match.index)));
        var fallback = document.createElement('span');
        fallback.className = 'question-math-fallback question-math-fallback-display';
        fallback.textContent = String(match[1] || '').trim();
        fragment.appendChild(fallback);
        cursor = match.index + match[0].length;
      }
      if (!changed) return;
      if (cursor < source.length) fragment.appendChild(document.createTextNode(source.slice(cursor)));
      textNode.parentNode.replaceChild(fragment, textNode);
    });
  }
  function run(){
    if (typeof renderMathInElement !== 'function') { done(); return; }
    try {
      renderMathInElement(document.body, {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '$', right: '$', display: false},
          {left: '\\(', right: '\\)', display: false},
          {left: '\\[', right: '\\]', display: true}
        ],
        throwOnError: true,
        strict: 'ignore',
        trust: false,
        errorCallback: function(){}
      });
    } catch (e) {}
    replaceFailedDisplayMath(document.body);
    requestAnimationFrame(function(){
      requestAnimationFrame(done);
    });
  }
  // This script is injected only after Playwright has populated the export DOM.
  // Calling it immediately avoids missing DOMContentLoaded on set_content pages.
  run();
})();
"""

# CDN fallback embedded in HTML (used only when local static bundle is missing).
EXPORT_KATEX_PDF_SCRIPT = r"""
<script src="%s/katex.min.js" crossorigin="anonymous"></script>
<script src="%s/contrib/auto-render.min.js" crossorigin="anonymous"></script>
<script>
%s
</script>
""" % (
    EXPORT_KATEX_CDN,
    EXPORT_KATEX_CDN,
    EXPORT_KATEX_PDF_RUN_SCRIPT.strip(),
)


def inject_katex_into_playwright_page(page) -> None:
    """
    Load bundled KaTeX from disk (no CDN). Playwright resolves ``fonts/`` relative to the CSS path.
    Falls back to jsDelivr when the vendor folder is absent (requires outbound network).
    """
    d = _EXPORT_KATEX_STATIC_DIR
    if katex_static_assets_available():
        page.add_style_tag(path=str(d / 'katex.min.css'))
        page.add_script_tag(path=str(d / 'katex.min.js'))
        page.add_script_tag(path=str(d / 'contrib' / 'auto-render.min.js'))
    else:
        page.add_style_tag(url=f'{EXPORT_KATEX_CDN}/katex.min.css')
        page.add_script_tag(url=f'{EXPORT_KATEX_CDN}/katex.min.js')
        page.add_script_tag(url=f'{EXPORT_KATEX_CDN}/contrib/auto-render.min.js')
        try:
            page.wait_for_function(
                'typeof renderMathInElement === "function"',
                timeout=30000,
            )
        except Exception:
            pass
    page.evaluate(EXPORT_KATEX_PDF_RUN_SCRIPT)
