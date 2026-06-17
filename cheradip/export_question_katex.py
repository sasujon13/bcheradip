"""
LaTeX source normalization for PDF/HTML export (mirrors fcheradip question-katex-render.ts).
KaTeX HTML is produced in Playwright via auto-render before page.pdf().
"""
from __future__ import annotations

import re

_ZW_CHARS_RE = re.compile(r'[\u200B-\u200D\uFEFF]')
_BOXED_TAIL_RE = re.compile(
    r'\$\$(\s*\\boxed\{(?:[^{}]|\{[^{}]*\})*\})\s*\$(?!\$)',
    re.DOTALL,
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
        out.append(s[open_:])
        break
    return ''.join(out)


def normalize_question_latex_source(text: str) -> str:
    """Same rules as Angular ``normalizeQuestionLatexSource`` before KaTeX."""
    if not text:
        return ''
    s = _ZW_CHARS_RE.sub('', str(text))
    s = re.sub(r'\\+\s*\$\$', '\n$$', s)
    s = _BOXED_TAIL_RE.sub(r'$$\1$$', s)
    return _close_unterminated_display_math(s)


# KaTeX 0.16.x — keep in sync with fcheradip package.json
EXPORT_KATEX_VERSION = '0.16.11'
EXPORT_KATEX_CDN = f'https://cdn.jsdelivr.net/npm/katex@{EXPORT_KATEX_VERSION}/dist'

EXPORT_KATEX_HEAD_HTML = f"""
  <link rel="stylesheet" href="{EXPORT_KATEX_CDN}/katex.min.css" crossorigin="anonymous" />
"""

# Runs after DOM + images; sets window.__katexPdfDone for Playwright.
EXPORT_KATEX_PDF_SCRIPT = r"""
<script src="%s/katex.min.js" crossorigin="anonymous"></script>
<script src="%s/contrib/auto-render.min.js" crossorigin="anonymous"></script>
<script>
(function(){
  function done(){ window.__katexPdfDone = true; }
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
        throwOnError: false,
        strict: 'ignore',
        trust: false
      });
    } catch (e) {}
    done();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
</script>
""" % (
    EXPORT_KATEX_CDN,
    EXPORT_KATEX_CDN,
)

EXPORT_KATEX_PDF_CSS = """
    .katex { font-size: 1em; color: inherit; }
    .katex-display { display: block; margin: 0.35em 0; overflow-x: auto; overflow-y: hidden; }
    .topic-question-line .katex-display { margin: 0.25em 0; }
"""
