# -*- coding: utf-8 -*-
"""
Mirror of fcheradip/src/app/shared/c-program-question-format.ts so PDF/DOCX export
preserves C layout when the DB holds plain text (no q-code-block yet).
"""
from __future__ import annotations

import re
from html import escape as html_escape

_BENGALI_RE = re.compile(r'[\u0980-\u09FF]')


def _looks_like_c_program_question(text: str) -> bool:
    s = (text or '').strip()
    if not s:
        return False
    has_anchor = bool(
        re.search(r'#\s*include\b', s, re.I)
        or re.search(
            r'\b(main|printf|scanf|clrscr|getch|print\s*f|scan\s*f|print|scan)\s*\(',
            s,
            re.I,
        )
    )
    has_c_signal = bool(
        re.search(
            r'\b(main|printf|scanf|clrscr|getch|for|while|if|switch|return|print\s*f|scan\s*f|print|scan)\b',
            s,
            re.I,
        )
        or re.search(r'<\s*(stdio|conio)\.h\s*>', s, re.I)
    )
    return has_anchor and has_c_signal


def _has_include_anchor(text: str) -> bool:
    return bool(re.search(r'#\s*include\b', text, re.I))


def _has_io_anchor(text: str) -> bool:
    return bool(
        re.search(
            r'\b(printf|scanf|print\s*f|scan\s*f|print|scan)\s*\(',
            text,
            re.I,
        )
    )


def _is_bengali_text(line: str) -> bool:
    return bool(_BENGALI_RE.search(line))


def _is_creative_bn_subpart_line(line: str) -> bool:
    t = line.strip()
    if re.match(r'^\s*[কখগঘ]\.', t):
        return True
    # ASCII parens + any Bengali letter (matches (ক) and variants).
    if re.match(r'^\s*\([\u0980-\u09FF]\)', t):
        return True
    return False


def _index_of_first_creative_subpart_line(lines: list[str]) -> int:
    for i, ln in enumerate(lines):
        if _is_creative_bn_subpart_line(ln):
            return i
    return -1


def _detach_creative_tail_from_code(code: str, after: str) -> tuple[str, str]:
    lines = (code or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    idx = _index_of_first_creative_subpart_line(lines)
    if idx < 0:
        return (code.strip(), after)
    tail = '\n'.join(lines[idx:]).strip()
    kept = '\n'.join(lines[:idx]).rstrip()
    merged_after = '\n'.join(x for x in (tail, after) if (x or '').strip())
    return (kept, merged_after)


def _is_code_anchor_line(line: str) -> bool:
    return bool(
        re.search(r'#\s*include\b', line, re.I)
        or re.search(
            r'\b(main|printf|scanf|clrscr|getch|print\s*f|scan\s*f|print|scan)\s*\(',
            line,
            re.I,
        )
    )


def _is_program_adjacent_line(line: str) -> bool:
    t = line.strip()
    if not t:
        return False
    if _is_creative_bn_subpart_line(line):
        return False
    if _is_bengali_text(t):
        return False
    return bool(
        re.search(r'[#<>{}();=,+\-*/%&\[\]"]', t)
        or re.search(
            r'\b(main|printf|scanf|clrscr|getch|for|while|if|switch|return|int|char|float|double|void)\b',
            t,
            re.I,
        )
    )


def _extract_program_block(
    input_text: str,
) -> tuple[str, str, str] | None:
    lines = (input_text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    anchor_indexes = [i for i, line in enumerate(lines) if _is_code_anchor_line(line)]
    if not anchor_indexes:
        return None
    start = anchor_indexes[0]
    end = anchor_indexes[-1]
    while start > 0 and _is_program_adjacent_line(lines[start - 1]):
        start -= 1
    while end < len(lines) - 1 and _is_program_adjacent_line(lines[end + 1]):
        end += 1
    code_lines = lines[start : end + 1]
    if not any(_is_code_anchor_line(ln) for ln in code_lines):
        return None
    before = '\n'.join(lines[:start]).strip()
    code = '\n'.join(code_lines).strip()
    after = '\n'.join(lines[end + 1 :]).strip()
    return (before, code, after)


def _should_increase_indent_for_next_line(line: str) -> bool:
    t = line.strip()
    if not t or t.startswith('#') or t.startswith('//') or t.startswith('/*') or t.startswith('*'):
        return False
    if t.endswith('{'):
        return True
    if t.endswith(';') or t.endswith('}') or t.endswith(':'):
        return False
    return True


def _normalize_brace_after_paren_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    for line in lines:
        trimmed = line.strip()
        prev = merged[-1].strip() if merged else ''
        if prev and re.search(r'\)\s*$', prev) and trimmed.startswith('{'):
            merged[-1] = re.sub(r'\s+$', '', prev) + ' {'
            rest = trimmed[1:].strip()
            if rest:
                merged.append(rest)
            continue
        if re.search(r'\)\s*\{', trimmed):
            brace_idx = trimmed.find('{')
            before_brace = trimmed[:brace_idx].rstrip()
            after_brace = trimmed[brace_idx + 1 :].strip()
            merged.append(before_brace + ' {')
            if after_brace:
                merged.append(after_brace)
            continue
        merged.append(trimmed)
    return merged


def _format_c_program(code: str) -> str:
    raw_lines = (code or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    lines = [ln.replace('\t', '    ').rstrip(' \t') for ln in raw_lines]
    lines = _normalize_brace_after_paren_lines(lines)
    out: list[str] = []
    indent = 0
    for raw_line in lines:
        trimmed = raw_line.strip()
        if not trimmed:
            if out and out[-1] != '':
                out.append('')
            continue
        line_indent = indent
        if trimmed.startswith('}'):
            line_indent = max(0, line_indent - 1)
            indent = line_indent
        if trimmed.startswith('#'):
            line_indent = 0
        out.append('%s%s' % ('    ' * line_indent, trimmed))
        if trimmed.startswith('#'):
            continue
        if trimmed.endswith('{'):
            indent = line_indent + 1
            continue
        if _should_increase_indent_for_next_line(trimmed):
            indent = line_indent + 1
            continue
        indent = line_indent
    text = '\n'.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _encode_code_html(code: str) -> str:
    parts = []
    for line in (code or '').split('\n'):
        parts.append(html_escape(line).replace(' ', '&nbsp;'))
    return '<br />'.join(parts)


def format_maybe_c_program_question_text(raw: str, *, emit_html: bool = True) -> str:
    """
    If text looks like a C program question, wrap the program in formatted output.
    emit_html=True: same as Angular (<span class="q-code-block"><code>…</code></span>).
    emit_html=False: plain text for DOCX (newlines + spaces, no HTML).
    """
    input_s = (raw or '').strip()
    if not input_s or 'q-code-block' in input_s.lower():
        return raw if raw is not None else ''
    if not _looks_like_c_program_question(input_s):
        return raw if raw is not None else ''

    block = _extract_program_block(input_s)
    if not block:
        return raw if raw is not None else ''
    before, code, after = block
    if not code:
        return raw if raw is not None else ''

    code, after = _detach_creative_tail_from_code(code, after)
    if not code.strip():
        return raw if raw is not None else ''

    code_line_count = len([ln for ln in code.split('\n') if ln.strip()])
    if not _has_include_anchor(code) and _has_io_anchor(code) and code_line_count <= 4:
        return raw if raw is not None else ''

    formatted = _format_c_program(code)
    if emit_html:
        block_html = (
            '<span class="q-code-block"><code>%s</code></span>'
            % _encode_code_html(formatted)
        )
        parts = [p for p in (before, block_html, after) if (p or '').strip()]
        return '\n'.join(parts)
    parts = [p for p in (before, formatted, after) if (p or '').strip()]
    return '\n'.join(parts)
