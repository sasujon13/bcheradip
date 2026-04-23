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
    has_classic_anchor = bool(
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
    has_glued_loop_or_branch = bool(
        re.search(r';\s*(?:for|while|if)\s*\(', s, re.I)
        or re.search(r'\bfor\s*\([^)]*\)\s*\{', s, re.I)
        or re.search(r'\bfor\s*\([^)]*\)\s*(?!\{)\s*\S', s, re.I)
        or (
            re.search(r'\bif\s*\([^)]*\)\s*\{', s, re.I)
            and ';' in s
            and '{' in s
        )
    )
    return (has_classic_anchor and has_c_signal) or has_glued_loop_or_branch


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


def _break_glued_include_and_following_word(line: str) -> str:
    s = re.sub(r'(#\s*include)\s*(?=[<"])', '#include ', line, flags=re.I)
    s = re.sub(r'\)\s*\{\s*,\s*(?=#\s*include)', ') {\n', s, flags=re.I)
    s = re.sub(
        r'(#include\s+<[^>]+>)(?=[^\s\n\r])',
        r'\1\n',
        s,
        flags=re.I,
    )
    s = re.sub(
        r'(#include\s+"[^"]+")(?=[^\s\n\r])',
        r'\1\n',
        s,
        flags=re.I,
    )
    s = re.sub(
        r'(#include\s+<[^>]+>)\s+(?=\S)',
        r'\1\n',
        s,
        flags=re.I,
    )
    return re.sub(
        r'(#include\s+"[^"]+")\s+(?=\S)',
        r'\1\n',
        s,
        flags=re.I,
    )


_DENSE_MIN_LEN = 12


def _line_has_reflowable_c_anchors(ct: str) -> bool:
    if _has_io_anchor(ct) or re.search(r'#\s*include\b', ct, re.I):
        return True
    if re.search(
        r'\b(main|printf|scanf|clrscr|getch)\s*\(',
        ct,
        re.I,
    ):
        return True
    if re.search(
        r';\s*(?:for|while|if|switch|int|char|void|float|double|return|continue|break|struct|static|unsigned|long)\b',
        ct,
        re.I,
    ):
        return True
    if re.search(r';\s*\{', ct):
        return True
    if re.search(r'\)\s*\{', ct):
        return True
    if re.search(
        r'\{\s*(?:if|for|while|continue|break|return|int|char|void|float|double)\b',
        ct,
        re.I,
    ):
        return True
    if re.search(r'\)\s*[A-Za-z_]\w*\s*=', ct):
        return True
    return False


def _line_looks_packed_one_line_c(ct: str, chunk: str) -> bool:
    if '\n' in chunk:
        return False
    if len(ct) < _DENSE_MIN_LEN or not re.search(r'[#;{}]', ct):
        return False
    if not _line_has_reflowable_c_anchors(ct):
        return False
    return True


def _should_reflow_c_layout(ct: str, chunk: str) -> bool:
    if '\n' in chunk:
        return False
    if re.search(r'#\s*include\s*<[^>]+>\s+\S', ct):
        return True
    if re.search(r'#\s*include\s*<[^>]+>[^\s#<"\']', ct):
        return True
    if re.search(
        r'\bmain\s*\([^)]*\)\s*(?:int|char|void|float|double|unsigned|#)',
        ct,
        re.I,
    ):
        return True
    return _line_looks_packed_one_line_c(ct, chunk)


_IO_CALL_HEAD_RE = re.compile(
    r'^(printf\s*\(|scanf\s*\(|print\s+f\s*\(|scan\s+f\s*\(|print\s*\(|scan\s*\()',
    re.I,
)


def _prev_non_space_char(s: str, before_index: int) -> str | None:
    j = before_index - 1
    while j >= 0 and s[j] in ' \t':
        j -= 1
    return s[j] if j >= 0 else None


def _needs_newline_before_glued_io_call(s: str, start: int) -> bool:
    prev = _prev_non_space_char(s, start)
    if prev is None:
        return False
    return bool(re.match(r'[0-9a-zA-Z_)}\]%]', prev))


def _insert_newlines_before_glued_io_calls(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    in_str: str | None = None
    line_comment = False
    block_comment = False
    while i < n:
        c = line[i]
        nxt = line[i + 1] if i + 1 < n else ''
        if line_comment:
            if c in '\r\n':
                line_comment = False
            out.append(c)
            i += 1
            continue
        if block_comment:
            if c == '*' and nxt == '/':
                out.append('*/')
                i += 2
                block_comment = False
                continue
            out.append(c)
            i += 1
            continue
        if in_str:
            if c == '\\' and i + 1 < n:
                out.append(c)
                out.append(line[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
            out.append(c)
            i += 1
            continue
        if c == '/' and nxt == '/':
            out.append('//')
            i += 2
            line_comment = True
            continue
        if c == '/' and nxt == '*':
            out.append('/*')
            i += 2
            block_comment = True
            continue
        if c in '"\'':
            in_str = c
            out.append(c)
            i += 1
            continue
        sub = line[i:]
        m = _IO_CALL_HEAD_RE.match(sub)
        if m:
            ln = len(m.group(0))
            if _needs_newline_before_glued_io_call(line, i):
                out.append('\n')
            out.append(line[i : i + ln])
            i += ln
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _densify_minified_ascii_c_line(line: str) -> str:
    glued = _insert_newlines_before_glued_io_calls(_break_glued_include_and_following_word(line))
    out: list[str] = []
    i = 0
    n = len(glued)
    paren = 0
    in_str: str | None = None
    line_comment = False
    block_comment = False
    while i < n:
        c = glued[i]
        nxt = glued[i + 1] if i + 1 < n else ''
        if line_comment:
            if c in '\r\n':
                line_comment = False
            out.append(c)
            i += 1
            continue
        if block_comment:
            if c == '*' and nxt == '/':
                out.append('*/')
                i += 2
                block_comment = False
                continue
            out.append(c)
            i += 1
            continue
        if in_str:
            if c == '\\' and i + 1 < n:
                out.append(c)
                out.append(glued[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
            out.append(c)
            i += 1
            continue
        if c == '/' and nxt == '/':
            out.append('//')
            i += 2
            line_comment = True
            continue
        if c == '/' and nxt == '*':
            out.append('/*')
            i += 2
            block_comment = True
            continue
        if c in '"\'':
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == '(':
            paren += 1
            out.append(c)
            i += 1
            continue
        if c == ')':
            paren = max(0, paren - 1)
            out.append(c)
            i += 1
            if paren == 0:
                j = i
                while j < n and glued[j] in ' \t':
                    j += 1
                if j < n:
                    nxt = glued[j]
                    if nxt == '{':
                        while i < j:
                            out.append(glued[i])
                            i += 1
                        out.append('\n')
                    elif nxt != '(' and nxt not in (';', ',', ')', ']', '.'):
                        rest = glued[j : j + 48]
                        stmt_head = bool(
                            re.match(
                                r'^(continue|break|return|if|for|while|switch|do|printf|scanf|sizeof)\b',
                                rest,
                                re.I,
                            )
                            or re.match(
                                r'^(int|char|void|float|double|unsigned|short|long|static|const|struct)\b',
                                rest,
                            )
                        )
                        glued_stmt = bool(
                            re.match(r'^[A-Za-z_]\w*\s*=', rest)
                            or re.match(r'^[A-Za-z_]\w*\s*\+\+', rest)
                            or re.match(r'^[A-Za-z_]\w*\s*--', rest)
                            or re.match(r'^[A-Za-z_]\w*\s*;', rest)
                        )
                        if stmt_head or glued_stmt:
                            while i < j:
                                out.append(glued[i])
                                i += 1
                            out.append('\n')
            continue
        if c == ';' and paren == 0:
            out.append(';')
            i += 1
            while i < n and glued[i] in ' \t':
                out.append(glued[i])
                i += 1
            if i < n and glued[i] == '}':
                out.append('\n')
                continue
            if i < n and not re.match(r'^[)\]}]', glued[i]):
                out.append('\n')
            continue
        if c == '{':
            out.append('{')
            i += 1
            if i < n and glued[i] not in '}\r\n':
                out.append('\n')
            continue
        if c == '}':
            out.append('}')
            i += 1
            while i < n and glued[i] in ' \t':
                out.append(glued[i])
                i += 1
            if i < n and glued[i] not in '};\r\n':
                out.append('\n')
            continue
        out.append(c)
        i += 1
    return ''.join(out).rstrip()


def _expand_dense_c_code_for_display(code: str) -> str:
    lines = (code or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    out: list[str] = []
    for raw in lines:
        t = raw.strip()
        if not t:
            out.append(raw)
            continue
        has_include_or_main = bool(
            re.search(r'#\s*include\b|\b(main|printf|scanf)\s*\(', raw, re.I)
        )
        if _is_bengali_text(raw) and not has_include_or_main:
            out.append(raw)
            continue
        prepped = _break_glued_include_and_following_word(raw)
        for chunk in prepped.split('\n'):
            ct = chunk.strip()
            if not ct:
                if chunk:
                    out.append(chunk)
                continue
            if _should_reflow_c_layout(ct, chunk):
                out.append(_densify_minified_ascii_c_line(ct))
            else:
                out.append(chunk)
    return '\n'.join(out)


def _is_bengali_text(line: str) -> bool:
    return bool(_BENGALI_RE.search(line))


def _is_bengali_narrative_only_line(trimmed: str) -> bool:
    if not _is_bengali_text(trimmed):
        return False
    if re.search(
        r'#\s*include\b|\bmain\s*\(|\b(int|char|void|float|double|short|long|unsigned|signed|static|const|struct|union|enum|return|for|if|else|while|do|switch|case|default|break|continue|goto|sizeof|typedef|extern|auto|register)\b|\b(printf|scanf|clrscr|getch)\b|print\s*f|scan\s*f|\bprint\s*\(|\bscan\s*\(',
        trimmed,
        re.I,
    ):
        return False
    return True


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


_C_LINE_START_RE = re.compile(
    r'(#\s*include\b|\b(?:void|int|char|float|double|long|short|signed|unsigned)\s+main\s*\(|\bmain\s*\(|\b(?:printf|scanf|print\s*f|scan\s*f|print|scan)\s*\()',
    re.I,
)


def _peel_bengali_around_c_on_line(line: str) -> tuple[str, str, str]:
    """Return (before_bn, c_only, after_bn) for one physical line."""
    raw = line
    if not raw.strip():
        return ('', raw, '')
    if not _is_bengali_text(raw):
        return ('', raw, '')

    before = ''
    s = raw
    m = _C_LINE_START_RE.search(s)
    if m and m.start() > 0:
        head = s[: m.start()]
        if _is_bengali_text(head):
            before = head.rstrip()
            s = s[m.start() :]
    elif not m:
        lb = s.rfind('}')
        if lb >= 0:
            tail0 = s[lb + 1 :]
            if tail0.strip() and _is_bengali_text(tail0):
                return ('', s[: lb + 1].strip(), tail0.strip())
        return (s.strip(), '', '')

    after = ''
    lb = s.rfind('}')
    if lb >= 0:
        tail = s[lb + 1 :]
        if tail.strip() and _is_bengali_text(tail):
            after = tail.strip()
            s = s[: lb + 1]
    return (before, s, after)


def _split_extracted_code_into_c_and_bn_segments(
    code: str,
) -> tuple[list[str], list[tuple[str, str]]]:
    """leading_bn; segments are ('code', str) or ('bn', str) — matches fcheradip c-program-question-format."""
    lines = (code or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    leading_bn: list[str] = []
    segments: list[tuple[str, str]] = []
    cur_code: list[str] = []

    def flush_code() -> None:
        if cur_code:
            joined = '\n'.join(cur_code).strip()
            if joined:
                segments.append(('code', joined))
            cur_code.clear()

    for ln in lines:
        pb, pc, pa = _peel_bengali_around_c_on_line(ln)
        if pb.strip():
            if not cur_code and not segments:
                leading_bn.append(pb.strip())
            else:
                flush_code()
                segments.append(('bn', pb.strip()))
        if pc.strip():
            cur_code.append(pc)
        if pa.strip():
            flush_code()
            segments.append(('bn', pa.strip()))
    flush_code()
    return (leading_bn, segments)


def _is_code_anchor_line(line: str) -> bool:
    if re.search(r'#\s*include\b', line, re.I):
        return True
    if re.search(
        r'\b(main|printf|scanf|clrscr|getch|print\s*f|scan\s*f|print|scan)\s*\(',
        line,
        re.I,
    ):
        return True
    if re.search(r';\s*(?:for|while|if)\s*\(', line, re.I):
        return True
    if re.search(r'^\s*(?:for|while|if)\s*\(', line, re.I):
        return True
    return False


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


def _is_braceless_control_header(line: str) -> bool:
    t = line.strip()
    if not t or '{' in t:
        return False
    if re.match(r'^\s*else\s*$', t, re.I):
        return True
    if not re.search(r'\)\s*$', t):
        return False
    return bool(re.match(r'^\s*(if|else\s+if|for|while|switch)\b', t, re.I))


def _braceless_single_stmt_indent_level(base: int, _header_line: str) -> int:
    return base + 1


def _should_increase_indent_for_next_line(line: str) -> bool:
    t = line.strip()
    if not t or t.startswith('#') or t.startswith('//') or t.startswith('/*') or t.startswith('*'):
        return False
    if t.endswith('{'):
        return True
    if t.endswith(';') or t.endswith('}') or t.endswith(':'):
        return False
    if _is_braceless_control_header(t):
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
    pending_braceless: tuple[int, str] | None = None
    for raw_line in lines:
        trimmed = raw_line.strip()
        if not trimmed:
            if out and out[-1] != '':
                out.append('')
            continue
        if _is_bengali_narrative_only_line(trimmed):
            out.append(trimmed)
            indent = 0
            pending_braceless = None
            continue
        if pending_braceless is not None:
            base, header = pending_braceless
            pending_braceless = None
            if _is_bengali_narrative_only_line(trimmed):
                out.append(trimmed)
                indent = 0
                continue
            body_indent = _braceless_single_stmt_indent_level(base, header)
            out.append('%s%s' % ('    ' * body_indent, trimmed))
            if trimmed.startswith('#'):
                indent = base
                continue
            if trimmed.endswith('{'):
                indent = body_indent + 1
                continue
            indent = base
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
        if _is_braceless_control_header(trimmed):
            pending_braceless = (line_indent, trimmed)
            continue
        if _should_increase_indent_for_next_line(trimmed):
            indent = line_indent + 1
            continue
        indent = line_indent
    text = '\n'.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _encode_code_html(code: str) -> str:
    parts = [html_escape(ln) for ln in (code or '').split('\n')]
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

    leading_bn, segments = _split_extracted_code_into_c_and_bn_segments(code)
    expanded_segments: list[tuple[str, str]] = []
    for kind, seg in segments:
        if kind == 'bn':
            expanded_segments.append((kind, seg))
        else:
            expanded_segments.append(('code', _expand_dense_c_code_for_display(seg)))

    code_only_joined = '\n'.join(s for k, s in expanded_segments if k == 'code').strip()
    if not code_only_joined:
        return raw if raw is not None else ''

    code_line_count = len([ln for ln in code_only_joined.split('\n') if ln.strip()])
    # Short printf/scanf-only fragments (no #include) stay plain; full `main` programs always get the code block.
    looks_like_full_main = bool(
        re.search(
            r'\b(?:void|int|char|float|double|long|short|unsigned|static)\s+main\s*\(|\bmain\s*\(',
            code_only_joined,
            re.I,
        )
    )
    if (
        not _has_include_anchor(code_only_joined)
        and _has_io_anchor(code_only_joined)
        and code_line_count <= 4
        and not looks_like_full_main
    ):
        return raw if raw is not None else ''

    merged_before = '\n'.join(x for x in ([before] + leading_bn) if (x or '').strip()).strip()
    middle_parts: list[str] = []
    for kind, seg in expanded_segments:
        if kind == 'code':
            formatted = _format_c_program(seg)
            if (formatted or '').strip():
                if emit_html:
                    middle_parts.append(
                        '<span class="q-code-block"><code>%s</code></span>'
                        % _encode_code_html(formatted)
                    )
                else:
                    middle_parts.append(formatted)
        elif (seg or '').strip():
            middle_parts.append(seg.strip())

    if emit_html:
        parts = [p for p in (merged_before, *middle_parts, after) if (p or '').strip()]
        return '\n'.join(parts)
    parts = [p for p in (merged_before, *middle_parts, after) if (p or '').strip()]
    return '\n'.join(parts)
