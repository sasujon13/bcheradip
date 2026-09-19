"""
Question / Explanation AI update requests for the Cheradip admin.

Queues edit requests ("Update Question" / "Update Explanation") for existing
questions by inserting rows into ``cheradip_pending_question_request`` — the SAME
mechanism the public ``/question`` page uses (PendingQuestionRequestView). The AI
cleaned/enriched text is NOT applied directly; reviewers approve or deny each row
in the admin table-data page (approve performs the UPDATE by qid on the subject table).

AI order: Home AI first, Cloud AI fallback (same services as exam-question creation).
"""
import base64
import difflib
import json
import logging
import re

from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)

_QUESTION_FIELDS = ('question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer', 'explanation')
# Everything else about a question (cleaned by the "Update Question" / "Update" action,
# never by the "Update Explanation" action).
_META_FIELDS = ('subject', 'subject_tr', 'chapter_no', 'chapter', 'topic_no', 'topic', 'type', 'level', 'subsource')


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


def _diff_html(old_text, new_text):
    """Character-level diff mirroring question.component.buildPendingEditDiffHtml.

    - added   -> <b style="color:blue">...</b>                  (new text)
    - removed -> <b><del style="color:darkred">...</del></b>     (old text)
    """
    sm = difflib.SequenceMatcher(None, str(old_text or ''), str(new_text or ''))
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            out.append(_escape_html(str(old_text or '')[i1:i2]))
            continue
        old_chunk = str(old_text or '')[i1:i2]
        new_chunk = str(new_text or '')[j1:j2]
        if old_chunk:
            out.append('<b><del style="color:darkred">%s</del></b>' % _escape_html(old_chunk))
        if new_chunk:
            out.append('<b style="color:blue">%s</b>' % _escape_html(new_chunk))
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


def _call_home_ai(prompt, max_tokens):
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
        logger.warning('Home AI question update failed: %s', exc)
        return None
    content = data.get('content') or data.get('explanation') or ''
    if not content or not str(content).strip():
        return None
    from cheradip.ai_question_generator import extract_json
    return _first_item(extract_json(content))


def _call_cloud_ai(prompt, max_tokens):
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
        logger.warning('Cloud AI question update failed: %s', exc)
        return None
    if not isinstance(data, dict):
        return None
    questions = data.get('questions') or data.get('items') or []
    if isinstance(questions, list) and questions and isinstance(questions[0], dict):
        return questions[0]
    return _first_item(data)


def _ask_ai(prompt, max_tokens=2000):
    """Home AI first, Cloud AI fallback. Returns (item_dict, provider)."""
    try:
        item = _call_home_ai(prompt, max_tokens)
        if item:
            return item, 'home-ai'
    except Exception as exc:  # noqa: BLE001
        logger.warning('Home AI question-update error: %s', exc)
    try:
        item = _call_cloud_ai(prompt, max_tokens)
        if item:
            return item, 'cloud'
    except Exception as exc:  # noqa: BLE001
        logger.warning('Cloud AI question-update error: %s', exc)
    return None, None


def _build_prompt(row, kind):
    """Prompt that asks the AI to reproduce the question with the cleaned fields."""
    def val(key):
        return str(row.get(key) or '')

    lines = []
    lines.append(
        "You are an expert editor for Bangladesh national curriculum exam questions (subject: "
        "'%s', level: %s, class: %s)." % (val('subject') or val('subject_tr'), val('level_tr'), val('class_level'))
    )
    if row.get('chapter_no') or row.get('chapter'):
        lines.append("Chapter: %s %s" % (val('chapter_no'), val('chapter')))
    if row.get('topic_no') or row.get('topic'):
        lines.append("Topic: %s %s" % (val('topic_no'), val('topic')))
    lines.append("qid: %s" % val('qid'))
    lines.append("Original JSON (do not change the meaning):")
    for field in _QUESTION_FIELDS + _META_FIELDS:
        lines.append('  "%s": %s' % (field, json.dumps(val(field), ensure_ascii=False)))
    lines.append('  "explanation2": %s' % json.dumps(val('explanation2'), ensure_ascii=False))
    lines.append('  "explanation3": %s' % json.dumps(val('explanation3'), ensure_ascii=False))
    if kind == 'question':
        lines.append("Task: review and correct the ENTIRE question record INCLUDING the explanation fields "
                     "(explanation, explanation2, explanation3). Remove unwanted symbols / artifacts / OCR noise / "
                     "stray punctuation from the question, options, answer, the explanation, and the "
                     "subject/chapter/topic/type/level metadata; fix spellings where clearly wrong; improve the "
                     "explanation where needed; and ensure `answer` exactly matches the text of the correct option. "
                     "Keep the meaning intact.")
    else:
        lines.append("Task: clean unwanted symbols from the EXPLANATION and improve it with more detail / correct "
                     "information where needed. Keep the QUESTION, OPTIONS, ANSWER and ALL metadata EXACTLY unchanged.")
    lines.append("IMPORTANT WORD-SPACING RULE: if any text appears as one long unbroken word, it is almost always "
                 "missing its spaces (e.g. joined Bangla sentences like 'দীর্ঘকালবিবেচনাকরাহলেউক্তশিল্পকারখানায়ব্যয়েরক্ষেত্রেপরিবর্তনহবে'). "
                 "Re-insert the natural spaces so it becomes understandable words and a meaningful sentence. "
                 "Do NOT leave such long joined text as-is.")
    lines.append("Reply with ONLY valid JSON, no markdown fences, in this exact shape:")
    lines.append('{"questions":[{"question":"...","option_1":"...","option_2":"...","option_3":"...","option_4":"...",'
                 '"answer":"...","subject":"...","subject_tr":"...","chapter_no":"...","chapter":"...",'
                 '"topic_no":"...","topic":"...","type":"...","level":"...","subsource":"...",'
                 '"explanation":"...","explanation2":"...","explanation3":"..."}]}')
    return "\n".join(lines)


def _cleaned_fields(item, kind):
    out = {}
    if kind == 'question':
        # the whole question record INCLUDING the explanation/2/3
        for key in ('question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer',
                    'explanation', 'explanation2', 'explanation3') + _META_FIELDS:
            out[key] = str(item.get(key) or '').strip()
    else:
        for key in ('explanation', 'explanation2', 'explanation3'):
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


def _clean_fields_ai(row, kind):
    item, provider = _ask_ai(_build_prompt(row, kind))
    if not item:
        return None, None
    return _cleaned_fields(item, kind), provider


def _has_changes(row, cleaned, kind):
    if kind == 'question':
        cleaned['subject_tr'] = (cleaned.get('subject_tr') or cleaned.get('subject')
                                 or row.get('subject_tr') or row.get('subject') or '')
        fields = ('question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer',
                  'explanation', 'explanation2', 'explanation3') + _META_FIELDS

        def effective(field):
            # AI value, or original when the AI dropped the field (no change).
            return str(cleaned.get(field) or '').strip() or str(row.get(field) or '')

        changed = any(_norm(effective(f)) != _norm(row.get(f)) for f in fields)
        if not effective('question'):
            return False
        if not _answer_consistent(cleaned):
            # keep the original answer when the AI repositioned/rewrote options
            cleaned['answer'] = row.get('answer')
        return changed
    fields = ('explanation', 'explanation2', 'explanation3')
    current = _norm(' '.join(str(row.get(f) or '') for f in fields))
    updated = _norm(' '.join(str(cleaned.get(f) or '') for f in fields))
    return bool(current != updated) and bool(cleaned.get('explanation') or '')


def _build_payload(row, cleaned, kind, table_name):
    """Payload for a pending update request (mirrors /question page submit).

    Content fields (question/options/answer/explanations) are wrapped with the
    CERADIP_PLAIN base64 prefix + char-level diff HTML so the admin review page
    shows changed portions in BOLD BLUE (new) / darkred strikethrough (old),
    exactly like the /question page edit requests. Unchanged fields stay plain.
    """
    qid = str(row.get('qid') or '')
    use_meta = kind == 'question'
    subject_tr = (cleaned.get('subject_tr') or cleaned.get('subject')
                  or row.get('subject_tr') or row.get('subject') or '').strip()[:255] if use_meta \
        else (str(row.get('subject_tr') or row.get('subject') or '').strip())[:255]

    # AI value (or original when the AI dropped it), compared against the ORIGINAL row text.
    def pick_content(field):
        ai_v = str(cleaned.get(field) or '').strip()
        return ai_v if ai_v else str(row.get(field) or '')

    # Metadata: AI value, or original when the AI dropped it (preserve, never blank).
    def pick_meta(field):
        ai_v = str(cleaned.get(field) or '').strip()
        return ai_v if ai_v else str(row.get(field) or '')

    # chapter/topic/subsource carry visible text: diff-wrap only when changed, like /question.
    def pick_text_meta(field):
        return _wrap_pending_field(row.get(field), pick_meta(field))

    return {
        'table': table_name,
        'requested_qid': qid or None,
        'qid': qid or None,
        'level_tr': (row.get('level_tr') or '')[:100],
        'class_level': (row.get('class_level') or '')[:50],
        'subject_tr': subject_tr,
        'chapter_no': (pick_meta('chapter_no') if use_meta else row.get('chapter_no') or '')[:50],
        'chapter': (pick_text_meta('chapter') if use_meta else row.get('chapter') or '')[:255],
        'topic_no': (pick_meta('topic_no') if use_meta else row.get('topic_no') or '')[:50],
        'topic': (pick_text_meta('topic') if use_meta else row.get('topic') or '')[:255],
        'question': _wrap_pending_field(row.get('question'), pick_content('question')),
        'option_1': _wrap_pending_field(row.get('option_1'), pick_content('option_1')),
        'option_2': _wrap_pending_field(row.get('option_2'), pick_content('option_2')),
        'option_3': _wrap_pending_field(row.get('option_3'), pick_content('option_3')),
        'option_4': _wrap_pending_field(row.get('option_4'), pick_content('option_4')),
        'answer': _wrap_pending_field(row.get('answer'), pick_content('answer')),
        'explanation': _wrap_pending_field(row.get('explanation'), pick_content('explanation')),
        'explanation2': _wrap_pending_field(row.get('explanation2'), pick_content('explanation2')),
        'explanation3': _wrap_pending_field(row.get('explanation3'), pick_content('explanation3')),
        'type': (pick_meta('type') if use_meta else row.get('type') or '')[:100],
        'level': (pick_meta('level') if use_meta else row.get('level') or '')[:100],
        'subsource': (pick_text_meta('subsource') if use_meta else row.get('subsource') or '')[:255],
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
    """Scan a subject question table and queue AI update requests (Update Question /
    Update Explanation) into cheradip_pending_question_request.

    Nothing is written to the subject table directly — a human reviews and approves
    (or denies) each pending row in the admin table-data page, exactly like updates
    submitted from the public /question page.
    """
    if db_alias not in connections:
        return {'message': 'Database not configured.'}
    kind = (kind or '').strip()
    if kind not in ('question', 'explanation'):
        return {'message': 'Unknown update kind: %s' % kind}
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
    failed = 0
    used = []
    for idx, row in enumerate(rows):
        qid = str(row.get('qid') or '')
        _emit(progress,
              phase='AI updating %s' % ('questions' if kind == 'question' else 'explanations'),
              current_qid=qid, current_table=table_name,
              processed=idx, total=total, pending_sent=pending_sent,
              percent=int(idx * 100 / total) if total else 100)
        try:
            cleaned, provider = _clean_fields_ai(row, kind)
            if not cleaned:
                failed += 1
                continue
            if not _has_changes(row, cleaned, kind):
                unchanged += 1
                continue
            payload = _build_payload(row, cleaned, kind, table_name)
            _insert_update_request(conn, payload)
            pending_sent += 1
            if provider:
                used.append(provider)
        except Exception as exc:  # noqa: BLE001
            logger.warning('Question update row %s failed: %s', qid, exc)
            failed += 1
    _emit(progress, phase='Done', current_qid='', current_table=table_name,
          processed=total, total=total, pending_sent=pending_sent, percent=100)

    label = 'Question' if kind == 'question' else 'Explanation'
    msg = '%s update: %d pending request(s) queued for review.' % (label, pending_sent)
    if unchanged:
        msg += ' %d already clean/unchanged.' % unchanged
    if failed:
        msg += ' %d could not be processed (AI unavailable or error).' % failed
    if used:
        msg += ' AI provider(s): %s.' % ', '.join(sorted(set(used)))
    return {'message': msg}


