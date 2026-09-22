"""
Question / Explanation AI update requests for the Cheradip admin.

Queues edit requests ("Update" / "AI Update") for existing questions by inserting rows into
``cheradip_pending_question_request`` — the SAME mechanism the public ``/question`` page uses
(PendingQuestionRequestView). Nothing is written to the subject table directly; reviewers approve
or deny each row in the admin table-data page (approve performs the UPDATE by qid on the subject
table).

Two passes, two buttons:

``special`` ("Update" — Home AI): unwanted *special characters* only.
    The whitelist-aware scanner (``cheradip.text_hygiene``) lists every code point that cannot
    belong to a Bangla/English question — invisible/zero-width, control, U+FFFD, private-use or
    unassigned, emoji, letters/digits pasted from another script that imitate Bangla/English,
    doubled or stranded Bangla signs, unusual spaces, unbalanced ``$``. Home AI confirms which of
    them are unwanted in this context, and only those characters are taken out — each one is
    marked in the pending request so the admin sees exactly what is removed before approving.
    Words, sentences, spelling, spacing, punctuation, every ``$…$``/``$$…$$``/``\\(…\\)``/
    ``\\[…\\]`` formula, every LaTeX/KaTeX/MathJax command and every HTML tag/script stay
    byte-for-byte; a normal sentence marker (``? ! . , ; :`` …) is never reported as junk.

``cloud`` ("AI Update" — Cloud AI): word/sentence correction.
    Each record goes to the Cloud AI proofreader as a Bangladesh education system item (national
    curriculum, Bangla medium) with the instruction to fix only genuine spelling / grammar /
    word-spacing / option-answer mistakes. The reply is post-checked — a field whose formula was
    damaged falls back to the original text — and the corrected fields become a pending request
    with the word-level diff the /question page shows.

Progress is reported by ``cheradip.exam_jobs`` as ``question_update_special`` /
``question_update_cloud``.
"""
import base64
import difflib
import json
import logging
import re
from collections import Counter

from django.conf import settings
from django.db import connections

from cheradip import text_hygiene

logger = logging.getLogger(__name__)

#: The two update passes behind the admin buttons (see the module docstring).
KIND_SPECIAL = 'special'      # Home AI: unwanted special characters only
KIND_CLOUD = 'cloud'          # Cloud AI: word/sentence correction
#: Legacy kind names of the old single "Update" action — they behave like the correction pass.
KIND_ALIASES = {'question': KIND_CLOUD, 'explanation': KIND_CLOUD}
#: Human labels for the job message.
KIND_LABELS = {KIND_SPECIAL: 'Special-character check', KIND_CLOUD: 'AI correction'}


def normalize_kind(kind):
    """Map a posted/legacy update kind onto a supported pass (``''`` when unknown)."""
    value = (kind or '').strip().lower()
    value = KIND_ALIASES.get(value, value)
    return value if value in (KIND_SPECIAL, KIND_CLOUD) else ''


_QUESTION_FIELDS = ('question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer', 'explanation')
# Everything else about a question (content + visible metadata).
_META_FIELDS = ('subject', 'subject_tr', 'chapter_no', 'chapter', 'topic_no', 'topic', 'type', 'level', 'subsource')
# Every text field both passes cover (content + visible metadata).
_HYGIENE_FIELDS = _QUESTION_FIELDS + ('explanation2', 'explanation3') + _META_FIELDS
#: Fields whose value the review page renders as HTML, so the removed characters can be marked.
_MARKED_FIELDS = _QUESTION_FIELDS + ('explanation2', 'explanation3')


def _norm(s):
    """Light normalization for change detection (whitespace + lowercase)."""
    return re.sub(r'\s+', '', str(s or '').strip().lower())


_CERADIP_PLAIN_PREFIX = '<!--CERADIP_PLAIN:'


def _escape_html(s):
    """HTML-escape text so diff markup is safe (mirrors question.component.escapeHtml)."""
    return (str(s or '')
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


_WORD_UNIT_RE = re.compile(r'\S+\s*')


def _word_units(text):
    """Split text into word units: each word plus its trailing whitespace.

    Joining the returned units reproduces the original string exactly, so a
    word-level diff can rebuild the text without losing any spacing.
    """
    return _WORD_UNIT_RE.findall(str(text or ''))


def _anchor_before(old_s, start, prev_end):
    """Original text right before a portion — the reviewer's safe replace anchor.

    Uses the unchanged gap that follows the previous correction (that gap is still
    present in the live field even after earlier portions were accepted). Falls back
    to the plain preceding text when two corrections are directly adjacent.
    """
    gap = old_s[prev_end:start]
    if not gap.strip():
        gap = old_s[:start]
    return gap[-40:]


def _portion_tag(word, anchor):
    """Blue (corrected) portion tag, carrying its pre-portion original context."""
    if not anchor:
        return '<b style="color:blue">%s</b>' % _escape_html(word)
    return '<b style="color:blue" data-ctx="%s">%s</b>' % (_escape_html(anchor), _escape_html(word))


def _del_tag(word):
    """Original word (with its error letters) shown struck through."""
    return '<b><del style="color:darkred">%s</del></b>' % _escape_html(word)


def _diff_html(old_text, new_text):
    """Word-level diff for the pending-question review page.

    Portions are whole words or whole phrases (never broken character fragments), so
    the reviewer clicks a real corrected word — not a stray letter/syllable.

    Display order is CORRECTED WORD FIRST, then the original word with its error
    letters (so the reader sees "correct  original-error"):
      - corrected -> <b style="color:blue" data-ctx="...">word </b>
      - original  -> <b><del style="color:darkred">word </del></b>

    `data-ctx` is the original text preceding that portion; the review page sends it
    back so the backend replaces THAT occurrence in the live field instead of an
    earlier identical word. Unchanged words are emitted as plain escaped text.
    """
    old_s = str(old_text or '')
    new_s = str(new_text or '')
    if old_s == new_s:
        return _escape_html(old_s)

    old_units = _word_units(old_s)
    new_units = _word_units(new_s)
    # Character offset of every old unit, so each portion knows exactly where it is.
    old_offsets = []
    acc = 0
    for unit in old_units:
        old_offsets.append(acc)
        acc += len(unit)
    old_offsets.append(acc)

    sm = difflib.SequenceMatcher(None, old_units, new_units, autojunk=False)
    # Join neighbouring change runs that have no unchanged text between them (e.g. a
    # joined word splitting into two words) so one click fixes the whole run.
    blocks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if (blocks and tag != 'equal' and blocks[-1][0] != 'equal'
                and blocks[-1][2] == i1 and blocks[-1][4] == j1):
            blocks[-1] = ('replace', blocks[-1][1], i2, blocks[-1][3], j2)
            continue
        blocks.append((tag, i1, i2, j1, j2))

    out = []
    prev_end = 0
    for tag, i1, i2, j1, j2 in blocks:
        if tag == 'equal':
            out.append(_escape_html(''.join(old_units[i1:i2])))
            prev_end = old_offsets[i2]
            continue
        old_part = old_units[i1:i2]
        new_part = new_units[j1:j2]
        if len(old_part) == len(new_part):
            # One-for-one word corrections => one clickable whole-word portion each
            # (5 word corrections => 5 individually clickable portions).
            for k in range(len(old_part)):
                start = old_offsets[i1 + k]
                out.append(_portion_tag(new_part[k], _anchor_before(old_s, start, prev_end)))
                out.append(_del_tag(old_part[k]))
                prev_end = start + len(old_part[k])
            continue
        # Word count changed (a joined word split, a word added or removed): keep the
        # whole run as ONE portion so the correction stays a real word/phrase.
        anchor = _anchor_before(old_s, old_offsets[i1], prev_end)
        if new_part:
            out.append(_portion_tag(''.join(new_part), anchor))
        if old_part:
            out.append(_del_tag(''.join(old_part)))
        prev_end = old_offsets[i2]
    return ''.join(out)


def _wrap_pending_field(orig, cur):
    """Mirror question.component.pendingEditFieldValue.

    Unchanged -> plain original. Changed -> '<!--CERADIP_PLAIN:<base64 utf-8>-->' + diff HTML,
    so database_admin_views._strip_red_markup recovers the clean text on approve.
    """
    orig_s = str(orig or '')
    cur_s = str(cur or '')
    if cur_s == orig_s:
        return orig_s
    b64 = base64.b64encode(cur_s.encode('utf-8')).decode('ascii')
    return '%s%s-->%s' % (_CERADIP_PLAIN_PREFIX, b64, _diff_html(orig_s, cur_s))


def _emit(progress, **kw):
    if progress:
        try:
            progress(**kw)
        except Exception:
            pass


def _first_item(parsed):
    """Pull the first question dict out of an LLM JSON reply."""
    if not isinstance(parsed, dict):
        return None
    for key in ('questions', 'items'):
        val = parsed.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val[0]
    if 'question' in parsed or 'explanation' in parsed:
        return parsed
    return None


def _parse_reply(content):
    """JSON (dict/list) of an LLM reply, or ``None`` when the reply is not JSON."""
    if not content or not str(content).strip():
        return None
    from cheradip.ai_question_generator import extract_json
    try:
        return extract_json(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning('AI reply could not be parsed: %s', exc)
        return None


def _home_ai_reply(prompt, max_tokens):
    """Send one prompt to the Home AI (local model) and return the parsed reply."""
    url = (getattr(settings, 'HOME_AI_QUESTIONS_URL', '') or '').strip()
    if not url:
        return None
    timeout = int(getattr(settings, 'AI_QUESTIONS_TIMEOUT_SECONDS', 60) or 60)
    # Explicit single model -> Home AI takes the FAST /chat/sync path (_chat_single).
    # Passing model:null triggers Auto mode which runs multiple local LLMs in
    # parallel + a CPU synthesis call and takes >100s (Cloudflare tunnel times out
    # after ~60-100s, causing "context canceled" and all questions to fail).
    model = (getattr(settings, 'HOME_AI_QUESTIONS_MODEL', '') or '').strip() or None
    payload = {
        'messages': [{'role': 'user', 'content': prompt}],
        'model': model,
        'file_context': [],
        'stream': False,
        'max_tokens': max_tokens,
    }
    try:
        import requests
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning('Home AI request failed: %s', exc)
        return None
    return _parse_reply(data.get('content') or data.get('explanation') or '')


def _cloud_ai_reply(prompt, max_tokens):
    """Send one prompt to the Cloud AI (the Bangladesh proofreader service) and parse the reply."""
    url = (getattr(settings, 'CLOUD_AI_QUESTIONS_URL', '') or '').strip()
    if not url:
        return None
    timeout = int(getattr(settings, 'AI_QUESTIONS_TIMEOUT_SECONDS', 60) or 60)
    payload = {'prompt': prompt, 'count': 1, 'language_code': 'en'}
    try:
        import requests
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning('Cloud AI request failed: %s', exc)
        return None
    return data if isinstance(data, (dict, list)) else None


def _ask_special(prompt):
    """Home AI answers the unwanted-character check (no Cloud AI — this is a local check).

    Returns ``(reply, provider)``; the reply is the parsed Home AI answer (a dict/list) or ``None``
    when the Home AI is unreachable or answered with something that is not JSON.
    """
    try:
        reply = _home_ai_reply(prompt, max_tokens=800)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Home AI special-character check failed: %s', exc)
        return None, None
    if reply is None:
        return None, None
    return reply, 'home-ai'


def _ask_correction(prompt, max_tokens=2500):
    """Cloud AI corrects the text (Home AI only when the Cloud AI is unavailable).

    Returns ``(item, provider)`` with the first question/item dict of the reply.
    """
    try:
        reply = _cloud_ai_reply(prompt, max_tokens)
        item = _first_item(reply) if reply is not None else None
        if item:
            return item, 'cloud'
    except Exception as exc:  # noqa: BLE001
        logger.warning('Cloud AI correction error: %s', exc)
    try:
        item = _first_item(_home_ai_reply(prompt, max_tokens))
        if item:
            return item, 'home-ai'
    except Exception as exc:  # noqa: BLE001
        logger.warning('Home AI correction fallback error: %s', exc)
    return None, None


def _row_header(row):
    """One context line shared by both prompts (subject / level / class / chapter / topic / qid)."""
    def val(key):
        return str(row.get(key) or '')

    parts = ['subject: %s' % (val('subject') or val('subject_tr') or '—'),
             'level: %s' % (val('level_tr') or '—'),
             'class: %s' % (val('class_level') or '—')]
    if row.get('chapter_no') or row.get('chapter'):
        parts.append('chapter: %s %s' % (val('chapter_no'), val('chapter')))
    if row.get('topic_no') or row.get('topic'):
        parts.append('topic: %s %s' % (val('topic_no'), val('topic')))
    parts.append('qid: %s' % val('qid'))
    return ', '.join(parts)


def _build_special_prompt(row, findings, limit=60):
    """Concise Home AI prompt for the unwanted-character pass (characters only, no rewriting).

    ``findings`` is the :func:`cheradip.text_hygiene.scan_row` map of the code points to judge.
    Returns ``(prompt, candidates)``; the candidates are ``cheradip.text_hygiene.flatten_candidates``
    of the same map, so answer number *n* is ``candidates[n - 1]``.
    """
    lines = ['You check one question of the Bangladesh national curriculum (Bangla medium) for '
             'unwanted special characters. Record: %s.' % _row_header(row)]
    lines.append(text_hygiene.PROMPT_RULE)
    block, candidates = text_hygiene.build_prompt_block(row, findings, limit)
    lines.extend(block)
    return '\n'.join(lines), candidates


def _build_correction_prompt(row):
    """Concise Cloud AI prompt for the word/sentence correction pass.

    The record is presented as a Bangladesh education system item so the corrections follow the
    spelling, grammar and word spacing of the textbooks used in Bangladesh.
    """
    def val(key):
        return str(row.get(key) or '')

    lines = []
    lines.append('You proofread one item of the Bangladesh education system (national curriculum, '
                 'Bangla medium): it belongs to a Bangladeshi textbook, so correct the language to '
                 'the standard Bangla/English spelling, grammar and word spacing used there.')
    lines.append('Record: %s.' % _row_header(row))
    lines.append('Item JSON (do not change its meaning):')
    for field in _QUESTION_FIELDS + _META_FIELDS:
        lines.append('  "%s": %s' % (field, json.dumps(val(field), ensure_ascii=False)))
    lines.append('  "explanation2": %s' % json.dumps(val('explanation2'), ensure_ascii=False))
    lines.append('  "explanation3": %s' % json.dumps(val('explanation3'), ensure_ascii=False))
    lines.append('Task: correct ONLY real text errors, nothing else:')
    lines.append('  1. Bangla/English spelling and typing mistakes, and words wrongly joined or '
                 'wrongly split ("দীর্ঘকালবিবেচনাকরাহলে" -> "দীর্ঘকাল বিবেচনা করাহলে"): restore the '
                 'natural word spacing of a real sentence.')
    lines.append('  2. Missing or wrong punctuation, and an `answer` whose text does not exactly '
                 'match one of the four options (then align it to the correct option).')
    lines.append('  3. Keep the meaning, the option order, the numbers, the facts and every metadata '
                 'value; never rewrite, reword, expand, translate or "improve" correct text.')
    lines.append('  4. Every correction must be a complete real word — never output broken '
                 'fragments, stray letters or meaningless sequences. Leave a field unchanged when '
                 'you are not sure of the correct form.')
    lines.append('  5. Never change anything inside math or HTML: keep every LaTeX / KaTeX / MathJax '
                 'formula ($...$, $$...$$, \\(...\\), \\[...\\], \\frac \\sqrt \\theta …), its '
                 'delimiters and its numbers, and every tag or entity (<br>, <sub>, &times;) '
                 'byte-for-byte.')
    lines.append('  6. A field with no error must be echoed EXACTLY as the original text.')
    lines.append('IMPORTANT OUTPUT RULE: include EVERY field in the reply — question, option_1, '
                 'option_2, option_3, option_4, answer, subject, subject_tr, chapter_no, chapter, '
                 'topic_no, topic, type, level, subsource, explanation, explanation2, explanation3.')
    lines.append('Reply with ONLY valid JSON, no markdown fences, in this exact shape:')
    lines.append('{"questions":[{"question":"...","option_1":"...","option_2":"...","option_3":"...","option_4":"...",'
                 '"answer":"...","subject":"...","subject_tr":"...","chapter_no":"...","chapter":"...",'
                 '"topic_no":"...","topic":"...","type":"...","level":"...","subsource":"...",'
                 '"explanation":"...","explanation2":"...","explanation3":"..."}]}')
    return '\n'.join(lines)



def _cleaned_fields(item):
    """Every text field of the AI reply, stripped (a field it omitted becomes '')."""
    out = {}
    for key in _MARKED_FIELDS + _META_FIELDS:
        out[key] = str(item.get(key) or '').strip()
    return out


def _answer_consistent(cleaned):
    """`answer` must correspond to one of the cleaned options (text or A-D/1-4)."""
    answer = _norm(cleaned.get('answer'))
    if not answer:
        return False
    options = [_norm(cleaned.get(k)) for k in ('option_1', 'option_2', 'option_3', 'option_4')]
    if answer in options:
        return True
    letter_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3, '1': 0, '2': 1, '3': 2, '4': 3}
    sel = letter_map.get((cleaned.get('answer') or '').strip().upper().rstrip('.'))
    return sel is not None and sel < len(options) and bool(options[sel])


def _clean_fields_ai(row):
    """Ask the Cloud AI proofreader for the corrected record. Returns ``(cleaned, provider)``."""
    item, provider = _ask_correction(_build_correction_prompt(row))
    if not item:
        return None, None
    return _cleaned_fields(item), provider


def _sanitize_fields(row, cleaned, fields):
    """Post-check the Cloud AI reply for unwanted characters and for damaged formulas.

    Mirrors :func:`cheradip.text_hygiene.sanitize_fields` over ``fields``: code points that are
    broken beyond doubt are dropped, and a field whose formula the AI altered is put back to the
    original text. Returns ``(notes, stats)``.
    """
    notes, stats = text_hygiene.sanitize_fields(row, cleaned, fields)
    for note in notes:
        logger.info('Question update qid %s: %s', row.get('qid'), note)
    return notes, stats


# ------------------------------------------------- Home AI: special chars ---
def _marker_badge(item):
    """Visible badge for one character the request takes out, e.g. ``⟦U+200B⟧``.

    A zero-width space or a look-alike letter is invisible in the review page, so every removed
    character is shown as a badge that carries its code point, Unicode name and kind (tooltip).
    """
    replacement = text_hygiene.finding_replacement(item)
    label = item.code_label + ('->space' if replacement == ' ' else '')
    return ('<del style="color:darkred;font-weight:700" title="%s %s (%s - removed)">⟦%s⟧</del>'
            % (item.code_label, _escape_html(item.name), _escape_html(item.kind), label))


def _removal_display(original, findings):
    """Original text with every affected character marked, so a reviewer can check each one.

    The words are the *cleaned* ones (what approve will write) — only the badge of a taken-out
    character is shown at the position it occupied. A replaced special space keeps its normal space
    next to the badge, so the word gap stays visible.
    """
    source = str(original or '')
    marked = {}
    for item in findings or ():
        if 0 <= item.index < len(source) and source[item.index] == item.char:
            marked[item.index] = item
    out = []
    for i, ch in enumerate(source):
        item = marked.get(i)
        if item is None:
            out.append(_escape_html(ch))
            continue
        replacement = text_hygiene.finding_replacement(item)
        if replacement:
            out.append(_escape_html(replacement))
        out.append(_marker_badge(item))
    return ''.join(out)


def _wrap_removal_field(original, cleaned, findings):
    """Pending value of one field for the special pass.

    Same convention as :func:`_wrap_pending_field` — ``<!--CERADIP_PLAIN:<base64>-->`` + display
    HTML — so approve and the Edit & Approve modal recover the cleaned text
    (:func:`backend.database_admin_views._strip_red_markup`); the badges are only the reviewer's
    mark of what is taken out.
    """
    original_s = str(original or '')
    cleaned_s = str(cleaned or '')
    if cleaned_s == original_s:
        return original_s
    b64 = base64.b64encode(cleaned_s.encode('utf-8')).decode('ascii')
    return '%s%s-->%s' % (_CERADIP_PLAIN_PREFIX, b64, _removal_display(original_s, findings))


def _split_sure(findings):
    """Split the removable findings of a record into the definitely-broken ones and the rest.

    Report-only findings (:data:`cheradip.text_hygiene.REPORT_ONLY_KINDS`, e.g. an unbalanced ``$``)
    are left out of both sets: they are named in the job message for a manual check but are never
    queued as a removal.
    """
    sure, ask = {}, {}
    for field, items in findings.items():
        items = text_hygiene.removable(items)
        definite = text_hygiene.sure_removals(items)
        rest = [item for item in items if item not in definite]
        if definite:
            sure[field] = definite
        if rest:
            ask[field] = rest
    return sure, ask
def _as_list(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _as_number(value):
    """1-based candidate number of an answer entry (``None`` when it is not a number)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    m = re.match(r'^\s*#?\s*(\d{1,4})\b', str(value or ''))
    return int(m.group(1)) if m else None


def _answer_numbers(reply):
    """Candidate numbers of a Home AI answer, as ``[(number, field), …]`` (``field`` may be '').

    Accepts the documented ``{"remove": {"question": [1, 3]}}`` plus the shapes a small local model
    may answer with instead: a bare number list (``[1, 3]``) and ``[{"field": …, "number": …}]``.
    """
    data = reply
    if isinstance(data, dict) and 'remove' in data:
        data = data.get('remove')
    numbers = []
    if isinstance(data, dict):
        for field, values in data.items():
            for value in _as_list(values):
                number = _as_number(value)
                if number:
                    numbers.append((number, str(field)))
        return numbers
    for value in _as_list(data):
        if isinstance(value, dict):
            number = _as_number(value.get('number') or value.get('candidate') or value.get('index'))
            if number:
                numbers.append((number, str(value.get('field') or '')))
        else:
            number = _as_number(value)
            if number:
                numbers.append((number, ''))
    return numbers


def _confirm_removals(row, findings):
    """Ask Home AI which suspicious code points are unwanted in this record.

    Returns ``(confirmed, provider)``; ``confirmed`` maps a field to the findings the AI listed
    (its numbers are 1-based positions in the numbered candidate list). Returns ``(None, None)``
    when Home AI is unreachable or the answer is unusable, so the caller reports the record as
    unverified instead of guessing.
    """
    prompt, candidates = _build_special_prompt(row, findings)
    if not candidates:
        return {}, None
    reply, provider = _ask_special(prompt)
    if reply is None:
        return None, None
    chosen = {}
    for number, field in _answer_numbers(reply):
        if not 1 <= number <= len(candidates):
            continue
        cand_field, item = candidates[number - 1]
        if field and field != cand_field:
            continue      # the number and the field disagree: trust the numbering
        chosen.setdefault(cand_field, []).append(item)
    return chosen, provider


def _special_clean(row, fields):
    """Home AI pass for one record: only the unwanted characters are taken out.

    Returns ``(cleaned, removals, provider, stats)``:

    * ``cleaned`` — ``{field: text}`` of the fields that really change (``None`` when nothing is
      taken out, so such a record queues no request at all),
    * ``removals`` — ``{field: [Finding, …]}``, the code points taken out of each changed field
      (used to mark them in the pending request),
    * ``stats`` — the counters/sample of the job message (``findings``, ``fields``, ``sure``,
      ``ai``, ``removed``, ``kept``, ``unverified``, ``codes``, ``sample``).

    Words, sentences, punctuation, spacing, formulas and HTML are never touched: the only edits are
    :func:`cheradip.text_hygiene.fix_findings` deletions/replacements of accepted code points.
    """
    stats = {'findings': 0, 'fields': 0, 'sure': 0, 'ai': 0, 'removed': 0, 'kept': 0,
             'check': 0, 'unverified': False, 'codes': Counter(), 'sample': None}
    findings = text_hygiene.scan_row(row, fields)
    if not findings:
        return None, {}, None, stats
    stats['fields'] = len(findings)
    stats['findings'] = sum(len(items) for items in findings.values())
    stats['check'] = sum(len(items) - len(text_hygiene.removable(items))
                         for items in findings.values())
    for items in findings.values():
        for item in items:
            stats['codes'][(item.code, item.name)] += 1
    first_field, first_items = next(iter(findings.items()))
    stats['sample'] = (first_field, text_hygiene.summarize(first_items, limit=2))

    sure, ask = _split_sure(findings)
    stats['sure'] = sum(len(items) for items in sure.values())
    confirmed, provider = {}, None
    if ask:
        confirmed, provider = _confirm_removals(row, ask)
        if confirmed is None:
            # Home AI unreachable: the definitely-broken code points may still be taken out.
            confirmed = {}
            stats['unverified'] = True
    stats['ai'] = sum(len(items) for items in confirmed.values())

    accepted = {}
    for field, items in list(sure.items()) + list(confirmed.items()):
        accepted.setdefault(field, []).extend(items)

    cleaned, removals = {}, {}
    for field, items in accepted.items():
        original = str(row.get(field) or '')
        fixed, applied = text_hygiene.fix_findings(original, items)
        if not applied:
            continue
        if not fixed.strip() and original.strip():
            # Never blank a field: everything it held was taken out, so let the admin look at that
            # record instead of queueing an empty value.
            logger.info('qid %s: %s would become empty after the character fix - skipped',
                        row.get('qid'), field)
            continue
        cleaned[field] = fixed
        removals[field] = applied
        stats['removed'] += len(applied)
    stats['kept'] = stats['findings'] - stats['removed']
    return (cleaned or None), removals, provider, stats


# --------------------------------------------------------------- message ---
def _codes_label(counter, limit=5):
    """Human list of the most common code points, e.g. ``U+200B ZERO WIDTH SPACE x11``."""
    parts = []
    for (code, name), count in counter.most_common(limit):
        label = 'U+%04X %s' % (code, name)
        parts.append('%s x%d' % (label, count) if count > 1 else label)
    return ', '.join(parts)


def _special_summary(stats):
    """Job-message fragment of the Home AI character pass ('' when nothing was found)."""
    if not stats.get('findings'):
        return ''
    msg = (' Unwanted characters: %d code point(s) in %d field(s) of %d record(s)'
           % (stats['findings'], stats['fields'], stats['rows']))
    if stats.get('codes'):
        msg += ' — %s' % _codes_label(stats['codes'])
    msg += '. %d taken out and marked in the pending request(s); %d kept by Home AI as correct here.' % (
        stats['removed'], stats['kept'])
    if stats.get('check'):
        msg += (' %d suspicious math delimiter(s) need a manual check — a stray $ is reported, never '
                'removed.' % stats['check'])
    if stats.get('unverified'):
        msg += ' %d record(s) could not be checked (Home AI unreachable) — rescan them later.' % (
            stats['unverified'])
    for qid, field, detail in list(stats.get('samples') or [])[:3]:
        msg += ' e.g. qid %s %s: %s;' % (qid, field, detail)
    return msg.rstrip(';')


def _has_changes(row, cleaned):
    """True when the Cloud AI reply really changes the record (correction pass).

    The `answer` field is first pulled back to the original when it no longer matches any option,
    so a reply that only repositioned/rewrote the options can never store an inconsistent answer.
    """
    cleaned['subject_tr'] = (cleaned.get('subject_tr') or cleaned.get('subject')
                             or row.get('subject_tr') or row.get('subject') or '')

    def effective(field):
        # AI value, or original when the AI dropped the field (no change).
        return str(cleaned.get(field) or '').strip() or str(row.get(field) or '')

    if not effective('question'):
        return False
    if not _answer_consistent(cleaned):
        # keep the original answer when the AI repositioned/rewrote options
        cleaned['answer'] = row.get('answer')
    return any(_norm(effective(f)) != _norm(row.get(f)) for f in _MARKED_FIELDS + _META_FIELDS)


def _build_payload(row, cleaned, kind, table_name, removals=None):
    """Payload for a pending update request (mirrors the /question page submit).

    ``kind='cloud'``: content fields are wrapped with the CERADIP_PLAIN base64 prefix + WORD-level
    diff HTML, so the review page shows the corrected word FIRST in BOLD BLUE and the original word
    with its errors right after it as darkred strikethrough — exactly like the /question page edit
    requests. Unchanged fields stay plain.

    ``kind='special'``: a changed content field carries the base64 plain cleaned text plus the
    marked characters (``⟦U+200B⟧`` badges, see :func:`_wrap_removal_field`), while ``removals``
    lists the code points taken out of each field. Metadata keeps the cleaned value as before (its
    change is a single invisible code point, so a badge would not be readable).
    """
    qid = str(row.get('qid') or '')
    removals = removals or {}

    def pick(field):
        """Cleaned value when the pass changed that field, else the original row text."""
        if field in cleaned:
            return cleaned.get(field)
        return row.get(field)

    def pick_text(field, limit):
        return str(pick(field) or '').strip()[:limit]

    subject_tr = pick_text('subject_tr', 255) or str(row.get('subject') or '').strip()[:255]

    def wrap(field, limit=None):
        """Review value of a visible field: marked (special pass) or diff-wrapped (correction).

        The value never exceeds the column limit: when the badge/diff markup would not fit, the
        cleaned plain text is used instead, so the INSERT can neither fail nor store cut markup.
        """
        original = str(row.get(field) or '')
        value = str(pick(field) or '')
        if limit:
            original = original[:limit]
            value = value[:limit]
        if field not in cleaned or value == original:
            return original
        if kind == KIND_SPECIAL:
            marked = _wrap_removal_field(original, value, removals.get(field))
        else:
            marked = _wrap_pending_field(original, value)
        if limit and len(marked) > limit:
            return value
        return marked

    return {
        'table': table_name,
        'requested_qid': qid or None,
        'qid': qid or None,
        'level_tr': (row.get('level_tr') or '')[:100],
        'class_level': (row.get('class_level') or '')[:50],
        'subject_tr': subject_tr,
        'chapter_no': pick_text('chapter_no', 50),
        'chapter': wrap('chapter', 255),
        'topic_no': pick_text('topic_no', 50),
        'topic': wrap('topic', 255),
        'question': wrap('question'),
        'option_1': wrap('option_1'),
        'option_2': wrap('option_2'),
        'option_3': wrap('option_3'),
        'option_4': wrap('option_4'),
        'answer': wrap('answer'),
        'explanation': wrap('explanation'),
        'explanation2': wrap('explanation2'),
        'explanation3': wrap('explanation3'),
        'type': pick_text('type', 100),
        'level': pick_text('level', 100),
        'subsource': wrap('subsource', 255),
        'status': 'Update',
        'updated_by': 'Cheradip AI',
    }


def _insert_update_request(conn, payload):
    """Insert a pending update row, auto-detecting the optional columns
    (table, requested_qid, qid, level, subsource, updated_by)."""
    base_cols = [
        'level_tr', 'class_level', 'subject_tr', 'chapter_no', 'chapter',
        'topic_no', 'topic', 'question', 'option_1', 'option_2', 'option_3',
        'option_4', 'answer', 'explanation', 'explanation2', 'explanation3',
        'type', 'status', 'created_at',
    ]
    cols = list(base_cols)
    vals = [payload.get(c) for c in base_cols]
    from django.utils import timezone
    vals[-1] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')

    with conn.cursor() as cur:
        def has_col(name):
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() "
                "AND table_name = 'cheradip_pending_question_request' AND column_name = %s", [name]
            )
            return cur.fetchone() is not None

        for extra in ('table', 'requested_qid', 'qid', 'level', 'subsource', 'updated_by'):
            if has_col(extra):
                cols.append(extra)
                vals.append(payload.get(extra))
        col_sql = ', '.join('`%s`' % c for c in cols)
        placeholders = ', '.join(['%s'] * len(cols))
        cur.execute(
            "INSERT INTO cheradip_pending_question_request (%s) VALUES (%s)" % (col_sql, placeholders),
            vals,
        )
        return cur.lastrowid


def run_question_update_job(db_alias, table_name, kind, progress=None, chapter_list=None, topic_list=None):
    """Scan a subject question table and queue pending update requests into
    cheradip_pending_question_request.

    ``kind`` is :data:`KIND_SPECIAL` (Home AI marks the unwanted special characters in the
    question, options, answer, explanations and metadata) or :data:`KIND_CLOUD` (the Cloud AI
    proofreader corrects words and sentences). Nothing is written to the subject table directly — a
    human reviews and approves (or denies) each pending row in the admin table-data page, exactly
    like updates submitted from the public /question page.
    """
    if db_alias not in connections:
        return {'message': 'Database not configured.'}
    kind = normalize_kind(kind)
    if not kind:
        return {'message': 'Unknown update kind — use "special" (characters) or "cloud" (words).'}
    table_name = ((table_name or '').strip().lower()).replace('`', '')
    if not table_name:
        return {'message': 'No table selected.'}
    conn = connections[db_alias]

    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
            [table_name],
        )
        if not cur.fetchone():
            return {'message': 'Table not found: %s' % table_name}
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() "
            "AND table_name = 'cheradip_pending_question_request'"
        )
        if not cur.fetchone():
            return {
                'message': 'This database has no cheradip_pending_question_request table — '
                           'updates cannot be queued here.'
            }
        # Only request columns that actually exist on the selected table.
        cur.execute(
            "SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            [table_name],
        )
        existing_cols = set((cur.fetchone()[0] or '').split(','))
        if 'qid' not in existing_cols or 'question' not in existing_cols:
            return {
                'message': 'Table \'%s\' is not a subject question table (it has no qid/question '
                           'columns) — question updates can only be queued for question tables.' % table_name
            }
        wanted = [
            'qid', 'subject', 'subject_tr', 'level_tr', 'class_level',
            'chapter_no', 'chapter', 'topic_no', 'topic', 'question',
            'option_1', 'option_2', 'option_3', 'option_4',
            'answer', 'explanation', 'explanation2', 'explanation3',
            'type', 'level', 'subsource',
        ]
        fields = [f for f in wanted if f in existing_cols]
        select_sql = ', '.join('`%s`' % f for f in fields)
        where = "question IS NOT NULL AND TRIM(COALESCE(question, '')) != ''"
        params = []
        if chapter_list:
            ph = ', '.join(['%s'] * len(chapter_list))
            where += " AND (chapter_no IN (%s) OR chapter IN (%s))" % (ph, ph)
            params += list(chapter_list) + list(chapter_list)
        if topic_list:
            ph = ', '.join(['%s'] * len(topic_list))
            where += " AND topic IN (%s)" % ph
            params += list(topic_list)
        cur.execute(
            "SELECT %s FROM `%s` WHERE %s ORDER BY qid" % (select_sql, table_name.replace('`', '``'), where),
            params,
        )
        rows = [dict(zip(fields, r)) for r in cur.fetchall()]

    total = len(rows)
    _emit(progress, phase='Preparing', current_qid='', current_table=table_name,
          processed=0, total=total, pending_sent=0, percent=0)
    pending_sent = 0
    unchanged = 0
    clean_rows = 0
    kept_rows = 0
    failed = 0
    reverted = 0
    used = []
    # Home AI character-pass counters (see _special_summary).
    char_stats = {'findings': 0, 'fields': 0, 'sure': 0, 'ai': 0, 'removed': 0, 'kept': 0,
                  'check': 0, 'unverified': 0, 'rows': 0, 'codes': Counter(), 'samples': []}
    phase = ('Home AI checking characters' if kind == KIND_SPECIAL
             else 'Cloud AI correcting words')
    for idx, row in enumerate(rows):
        qid = str(row.get('qid') or '')
        _emit(progress, phase=phase, current_qid=qid, current_table=table_name,
              processed=idx, total=total, pending_sent=pending_sent,
              percent=int(idx * 100 / total) if total else 100)
        try:
            if kind == KIND_SPECIAL:
                cleaned, removals, provider, row_stats = _special_clean(row, _HYGIENE_FIELDS)
                if row_stats['findings']:
                    char_stats['rows'] += 1
                    for key in ('findings', 'fields', 'sure', 'ai', 'removed', 'kept', 'check'):
                        char_stats[key] += row_stats[key]
                    char_stats['codes'].update(row_stats['codes'])
                    if row_stats['unverified']:
                        char_stats['unverified'] += 1
                    if row_stats['sample'] and len(char_stats['samples']) < 40:
                        field, detail = row_stats['sample']
                        char_stats['samples'].append((qid, field, detail))
                if not cleaned:
                    # Nothing to review for this record: either no character at all, or Home AI
                    # judged every candidate correct in this context.
                    if row_stats['findings']:
                        kept_rows += 1
                    else:
                        clean_rows += 1
                    continue
                _insert_update_request(
                    conn, _build_payload(row, cleaned, kind, table_name, removals=removals))
                pending_sent += 1
                if provider:
                    used.append(provider)
                continue
            # Cloud AI correction pass.
            cleaned, provider = _clean_fields_ai(row)
            if not cleaned:
                failed += 1
                continue
            _notes, clean_stats = _sanitize_fields(row, cleaned, _HYGIENE_FIELDS)
            reverted += len(clean_stats['reverted'])
            if not _has_changes(row, cleaned):
                unchanged += 1
                continue
            _insert_update_request(
                conn, _build_payload(row, cleaned, kind, table_name))
            pending_sent += 1
            if provider:
                used.append(provider)
        except Exception as exc:  # noqa: BLE001
            logger.warning('Question update row %s failed: %s', qid, exc)
            failed += 1
    _emit(progress, phase='Done', current_qid='', current_table=table_name,
          processed=total, total=total, pending_sent=pending_sent, percent=100)

    msg = '%s: %d pending request(s) queued for review.' % (KIND_LABELS[kind], pending_sent)
    if kind == KIND_SPECIAL:
        if clean_rows:
            msg += ' %d record(s) were already free of unwanted characters.' % clean_rows
        if kept_rows:
            msg += (' %d record(s) kept their suspicious characters (Home AI judged them correct '
                    'here).' % kept_rows)
    elif unchanged:
        msg += ' %d record(s) already correct/unchanged.' % unchanged
    if failed:
        msg += ' %d record(s) could not be processed (AI unavailable or invalid reply).' % failed
    if reverted:
        msg += ' %d field(s) were put back because the Cloud AI reply damaged a formula.' % reverted
    if kind == KIND_SPECIAL:
        msg += _special_summary(char_stats)
    else:
        msg += (' Approve or deny each request in the table below — nothing is applied to the '
                'records until you do.')
    if used:
        msg += ' AI provider(s): %s.' % ', '.join(sorted(set(used)))
    return {
        'message': msg,
        'characters_found': char_stats['findings'],
        'characters_removed': char_stats['removed'],
        'characters_kept': char_stats['kept'],
        'characters_unverified_rows': char_stats['unverified'],
        'fields_reverted': reverted,
    }


