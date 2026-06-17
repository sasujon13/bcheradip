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
    s = _ZW_CHARS_RE.sub('', str(text))
    s = re.sub(r'\\+\s*\$\$', '\n$$', s)
    s = _BOXED_TAIL_RE.sub(r'$$\1$$', s)
    s = _normalize_inline_math_tex(s)
    return _close_unterminated_display_math(s)


# Legacy CDN fallback (dev machines with network but missing static bundle).
EXPORT_KATEX_CDN = f'https://cdn.jsdelivr.net/npm/katex@{EXPORT_KATEX_VERSION}/dist'

EXPORT_KATEX_HEAD_HTML = f"""
  <link rel="stylesheet" href="{EXPORT_KATEX_CDN}/katex.min.css" crossorigin="anonymous" />
"""

EXPORT_KATEX_PDF_CSS = """
    .katex { font-size: 1em; color: inherit; }
    .katex-display { display: block; margin: 0.35em 0; overflow-x: auto; overflow-y: hidden; }
    .topic-question-line .katex-display { margin: 0.25em 0; }
"""

# Inline runner when assets are injected via page.add_style_tag / add_script_tag (local bundle).
EXPORT_KATEX_PDF_RUN_SCRIPT = r"""
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
    requestAnimationFrame(function(){
      requestAnimationFrame(done);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
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
