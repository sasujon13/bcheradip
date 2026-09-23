"""Bounded, read-only retrieval from the published question bank for tutor replies."""
import hashlib
import html
import json
import logging
import re
from django.core.cache import cache
from django.db import connections
from django.db.models import Q
from .models import TutorTopicIndex
from .subject_question_tables import subject_question_table_name
from .tutor_stream import unusable

logger = logging.getLogger(__name__)
FIELDS = ('qid', 'id', 'chapter', 'chapter_no', 'topic', 'question', 'option_1',
          'option_2', 'option_3', 'option_4', 'answer', 'explanation', 'explanation2', 'explanation3')
STOP = set(('discuss details on explain describe what why how the a an is are of to in and for '
            'please briefly sentence sentences use one two three বিস্তারিত আলোচনা করুন সম্পর্কে কী কি '
            'কেন কিভাবে কীভাবে এবং একটি এর এই বলুন দিন এক দুই তিন বাক্য বাক্যে সংক্ষেপে').split())
ALIASES = [('table', 'tables', 'টেবিল'), ('database', 'ডেটাবেজ', 'ডাটাবেজ'),
           ('algorithm', 'অ্যালগরিদম'), ('programming', 'প্রোগ্রামিং'),
           ('html', 'এইচটিএমএল'), ('binary', 'বাইনারি')]


def plain(value, limit=2500):
    value = str(value or '')
    if re.fullmatch(r'</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>', value.strip()):
        return value.strip()[:limit]  # A literal HTML tag can itself be an MCQ answer.
    if value.lstrip().startswith('{'):
        try:
            draft = json.loads(value)
            if isinstance(draft, dict) and isinstance(draft.get('blocks'), list):
                value = '\n'.join(str(b.get('text', '')) for b in draft['blocks'] if isinstance(b, dict))
        except (ValueError, TypeError):
            pass
    value = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '', value, flags=re.I | re.S)
    # Keep C includes and mathematical comparisons; strip only known HTML tags.
    value = re.sub(r'</?(?:p|div|span|br|b|i|u|strong|em|ul|ol|li|table|thead|tbody|tr|td|th|h[1-6]|pre|code|a|img|sup|sub)\b[^>]*>', ' ', value, flags=re.I)
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()[:limit]


def terms(text):
    text = re.sub(r'^(?:Discuss Details on\s+|বিস্তারিত আলোচনা করুন:\s*)', '', text or '', flags=re.I)
    words = [w.casefold() for w in re.split(r'[\s,;.!?।॥()\[\]{}:<>/\\"\-]+', text) if len(w) > 1]
    result = list(dict.fromkeys(w for w in words if w not in STOP))[:10]
    for group in ALIASES:
        if any(w in result for w in group):
            result.extend(w for w in group if w not in result)
    return result[:18]


def clean_scope(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError('Invalid learning context.')
    result = {}
    for field in ('level_tr', 'class_level', 'subject_tr', 'chapter', 'chapter_no', 'topic'):
        item = value.get(field, '')
        if not isinstance(item, str) or len(item) > 255:
            raise ValueError('Invalid learning context.')
        if item.strip():
            result[field] = item.strip()
    result['selected_topic'] = value.get('selected_topic') is True
    return result


def topic_candidates(scope, query_terms):
    qs = TutorTopicIndex.objects.using('default').filter(db_alias__in=['hsc', 'honours'])
    for field in ('level_tr', 'class_level', 'subject_tr'):
        if scope.get(field):
            qs = qs.filter(**{field: scope[field]})
    if scope.get('selected_topic') and scope.get('topic'):
        qs = qs.filter(topic=scope['topic'])
        if scope.get('chapter_no'):
            qs = qs.filter(chapter_no=scope['chapter_no'])
        elif scope.get('chapter'):
            qs = qs.filter(chapter=scope['chapter'])
        return list(qs.order_by('-question_count', 'id')[:3])
    if not query_terms:
        return []
    match = Q()
    for word in query_terms:
        match |= Q(topic__icontains=word) | Q(chapter__icontains=word)
    rows = list(qs.filter(match).order_by('-question_count', 'id')[:120])
    def rank(row):
        topic, chapter = row.topic.casefold(), row.chapter.casefold()
        return sum(10 if word == topic else 4 if word in topic else 1 if word in chapter else 0 for word in query_terms)
    rows.sort(key=rank, reverse=True)
    return rows[:3]


def source_columns(alias, table):
    key = 'tutor:columns:' + alias + ':' + table
    columns = cache.get(key)
    if columns is None:
        with connections[alias].cursor() as cursor:
            cursor.execute('SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s', [table])
            columns = {row[0] for row in cursor.fetchall()}
        cache.set(key, columns, 600)
    return columns


def question_rows(source, query_terms, exact_topic=True):
    alias, table = source['db_alias'], source['table_name']
    # Sources are derived from the server's catalog, never a client-supplied table.
    if alias not in ('hsc', 'honours') or alias not in connections or not re.fullmatch(r'cheradip_[a-z0-9_]+', table):
        return []
    columns = source_columns(alias, table)
    if 'question' not in columns:
        return []
    selected = [field for field in FIELDS if field in columns]
    clauses, params = [], []
    if source.get('chapter_no') and 'chapter_no' in columns:
        clauses.append('chapter_no = %s'); params.append(source['chapter_no'])
    elif source.get('chapter') and 'chapter' in columns:
        clauses.append('chapter = %s'); params.append(source['chapter'])
    if exact_topic and source.get('topic') and 'topic' in columns:
        clauses.append('topic = %s'); params.append(source['topic'])
    elif query_terms:
        search_fields = [f for f in ('question', 'answer', 'explanation', 'explanation2', 'explanation3') if f in columns]
        combined = 'CONCAT_WS(\' \', ' + ', '.join('`' + f + '`' for f in search_fields) + ')'
        clauses.append('(' + ' OR '.join(combined + ' LIKE %s' for _ in query_terms[:6]) + ')')
        params.extend('%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%' for word in query_terms[:6])
    else:
        return []
    pk = 'qid' if 'qid' in columns else 'id' if 'id' in columns else 'question'
    with connections[alias].cursor() as cursor:
        cursor.execute('SELECT ' + ', '.join('`' + f + '`' for f in selected) + ' FROM `' + table + '` WHERE ' +
                       ' AND '.join(clauses) + ' ORDER BY `' + pk + '` LIMIT %s', params + [60])
        records = [dict(zip(selected, row)) for row in cursor.fetchall()]
    records.sort(key=lambda row: sum(5 if word in plain(row.get('question')).casefold() else
                                    1 if word in plain(row.get('explanation')).casefold() else 0
                                    for word in query_terms), reverse=True)
    return [{**row, '_source': source} for row in records[:6]]


def fallback_source(scope):
    """Allow a bounded question-text lookup only inside a real selected subject."""
    if not all(scope.get(f) for f in ('level_tr', 'class_level', 'subject_tr')):
        return None
    for alias in ('hsc', 'honours'):
        if alias not in connections:
            continue
        with connections[alias].cursor() as cursor:
            cursor.execute('SELECT 1 FROM cheradip_subject WHERE level_tr = %s AND class_level = %s AND subject_tr = %s LIMIT 1',
                           [scope['level_tr'], scope['class_level'], scope['subject_tr']])
            if cursor.fetchone():
                return {**scope, 'db_alias': alias, 'table_name': subject_question_table_name(scope['level_tr'], scope['class_level'], scope['subject_tr'])}
    return None


def render_records(records):
    blocks, sources, seen = [], [], set()
    remaining = 16000
    for row in records:
        source = row['_source']
        identity = (source['db_alias'], source['table_name'], str(row.get('qid', row.get('id', ''))))
        if identity in seen:
            continue
        seen.add(identity)
        if not plain(row.get('question')) or not any(plain(row.get(f)) and not unusable(plain(row.get(f))) for f in ('answer', 'explanation', 'explanation2', 'explanation3')):
            continue
        ref = 'Q' + str(len(blocks) + 1)
        lines = [f'[{ref}] {source.get("subject_tr", "")} / {plain(row.get("chapter"))} / {plain(row.get("topic"))}']
        for field in ('question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer', 'explanation', 'explanation2', 'explanation3'):
            value = plain(row.get(field), 1700 if field.startswith('explanation') else 1200)
            if value and not unusable(value):
                lines.append(field + ': ' + value)
        block = '\n'.join(lines)
        if len(block) > remaining:
            continue
        blocks.append(block); remaining -= len(block)
        sources.append({'reference': ref, 'qid': identity[2], 'subject': source.get('subject_tr', ''),
                        'chapter': plain(row.get('chapter')), 'topic': plain(row.get('topic'))})
        if len(blocks) >= 8:
            break
    return {'text': '\n\n'.join(blocks), 'sources': sources, 'count': len(blocks)}


def retrieve(query, scope):
    key = 'tutor:knowledge:v1:' + hashlib.sha256(json.dumps([query, scope], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return {**cached, 'cached': True}
    words = terms(query)
    records = []
    try:
        for match in topic_candidates(scope, words):
            source = {field: getattr(match, field) for field in ('db_alias', 'table_name', 'level_tr', 'class_level', 'subject_tr', 'chapter', 'chapter_no', 'topic')}
            records.extend(question_rows(source, words))
        if not records:
            source = fallback_source(scope)
            if source:
                records = question_rows(source, words, exact_topic=bool(scope.get('selected_topic')))
        result = render_records(records)
        cache.set(key, result, 60)
        return {**result, 'cached': False}
    except Exception:
        logger.exception('Tutor reference lookup failed')
        return {'text': '', 'sources': [], 'count': 0, 'cached': False, 'unavailable': True}
