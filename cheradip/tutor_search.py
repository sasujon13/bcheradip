"""AI Tutor topic index + search helpers.

The question bank is spread over ~258 subject question tables
(``cheradip_{level}_{class}_{subject}``) inside the ``cheradip_hsc`` /
``cheradip_honours`` databases and holds hundreds of MB. Scanning them per
user keystroke is far too slow for the AI Tutor chatbox, so ``build_index()``
distils every table's distinct ``(chapter, topic)`` pairs into the compact
``cheradip_tutor_topic_index`` table (default DB). ``search()`` /
``related_topics()`` / ``sample_questions()`` then answer the chatbox
instantly.
"""
import hashlib
import logging
import re

from django.db import connections
from django.db.models import Q
from django.utils import timezone

from .subject_question_tables import subject_question_table_name

logger = logging.getLogger(__name__)

# Databases that hold subject question tables.
SCAN_ALIASES = ['hsc', 'honours']

# Lookup tables that are not subject question tables (defensive: we also
# require chapter/topic/question columns, but skip these by name too).
NON_QUESTION_TABLES = {
    'cheradip_subject',
    'cheradip_question_levels',
    'cheradip_question_classes',
    'cheradip_question_groups',
    'cheradip_question_subjects',
    'cheradip_question_chapters',
    'cheradip_question_topics',
    'cheradip_question_list',
    'cheradip_tutor_topic_index',
    'cheradip_pending_question',
    'django_migrations',
    'django_content_type',
}


def _table_columns(conn, table_name):
    """Set of column names for a table (cached per connection+table)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            [table_name],
        )
        return {r[0] for r in cur.fetchall()}


def _list_question_tables(conn):
    """Names of subject question tables in the given DB."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name LIKE 'cheradip\\_%'"
        )
        names = [r[0] for r in cur.fetchall()]
    out = []
    for name in names:
        if name in NON_QUESTION_TABLES:
            continue
        cols = _table_columns(conn, name)
        if 'chapter' in cols and 'topic' in cols and ('qid' in cols or 'id' in cols):
            out.append(name)
    return out


def _subject_map(conn):
    """Read cheradip_subject -> list of dicts incl. computed table_name."""
    with conn.cursor() as cur:
        try:
            cur.execute(
                "SELECT level_tr, class_level, subject_tr, subject_name "
                "FROM cheradip_subject ORDER BY id"
            )
            rows = cur.fetchall()
        except Exception as e:
            logger.debug('_subject_map: %s', e)
            return []
    seen = set()
    out = []
    for row in rows:
        lt = (row[0] or '').strip()
        cl = (row[1] or '').strip()
        st = (row[2] or '').strip()
        sn = (row[3] or '').strip() if len(row) > 3 and row[3] else ''
        if not st:
            continue
        key = (cl, st)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            'level_tr': lt,
            'class_level': cl,
            'subject_tr': st,
            'subject_name': sn,
            'table_name': subject_question_table_name(lt, cl, st),
        })
    return out


def _fingerprint(db_alias, table_name, chapter, topic):
    raw = '{}|{}|{}|{}'.format(db_alias or '', table_name or '', chapter or '', topic or '')
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def build_index(rebuild=True, verbose=False):
    """Scan subject question tables and (re)build cheradip_tutor_topic_index."""
    from .models import TutorTopicIndex

    if rebuild:
        TutorTopicIndex.objects.using('default').all().delete()

    total_rows = 0
    for alias in SCAN_ALIASES:
        if alias not in connections:
            logger.warning('build_tutor_index: alias %s not configured, skipping', alias)
            continue
        conn = connections[alias]
        try:
            tables = _list_question_tables(conn)
        except Exception as e:
            logger.warning('build_tutor_index: cannot list tables in %s: %s', alias, e)
            continue
        subject_map = _subject_map(conn)
        table_meta = {s['table_name']: s for s in subject_map}
        for table_name in tables:
            meta = table_meta.get(table_name, {})
            cols = _table_columns(conn, table_name)
            has_topic_no = 'topic_no' in cols
            group_cols = ['chapter_no', 'chapter']
            if has_topic_no:
                group_cols.append('topic_no')
            group_cols.append('topic')
            group_sql = ', '.join('`{}`'.format(c) for c in group_cols)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT {}, COUNT(*) FROM `{}` "
                        "WHERE chapter IS NOT NULL AND topic IS NOT NULL AND TRIM(topic) != '' "
                        "GROUP BY {}".format(group_sql, table_name, group_sql)
                    )
                    rows = cur.fetchall()
            except Exception as e:
                logger.warning('build_tutor_index: skip %s.%s: %s', alias, table_name, e)
                continue

            objs = []
            for row in rows:
                chapter_no = (row[0] or '').strip()
                chapter = (row[1] or '').strip()
                if has_topic_no:
                    topic_no = (row[2] or '').strip()
                    topic = (row[3] or '').strip()
                    cnt = row[4]
                else:
                    topic_no = ''
                    topic = (row[2] or '').strip()
                    cnt = row[3]
                if not topic:
                    continue
                objs.append(TutorTopicIndex(
                    fingerprint=_fingerprint(alias, table_name, chapter, topic),
                    db_alias=alias,
                    table_name=table_name,
                    level_tr=meta.get('level_tr', ''),
                    class_level=meta.get('class_level', ''),
                    subject_tr=meta.get('subject_tr', ''),
                    subject_name=meta.get('subject_name') or meta.get('subject_tr', ''),
                    chapter_no=chapter_no,
                    chapter=chapter,
                    topic_no=topic_no,
                    topic=topic,
                    question_count=int(cnt or 0),
                    built_at=timezone.now(),
                ))
            if objs:
                TutorTopicIndex.objects.using('default').bulk_create(
                    objs, ignore_conflicts=True, batch_size=500
                )
                total_rows += len(objs)
                if verbose:
                    print('{} / {}: {} topics'.format(alias, table_name, len(objs)))
    return total_rows


def _tokens(q):
    q = (q or '').strip()
    if not q:
        return []
    return [t for t in re.split(r'[\s,;.!?।॥()\-_+:/\\]+', q) if t]


def search(query, limit=8):
    """Rank matching topic-index rows for a user query. Returns list of TutorTopicIndex."""
    from .models import TutorTopicIndex

    tokens = _tokens(query)
    q = (query or '').strip()
    if not tokens:
        return list(TutorTopicIndex.objects.using('default').order_by('-question_count')[:limit])

    q_filter = Q()
    for t in tokens:
        q_filter |= (
            Q(topic__icontains=t)
            | Q(chapter__icontains=t)
            | Q(subject_name__icontains=t)
            | Q(subject_tr__icontains=t)
        )
    matches = list(TutorTopicIndex.objects.using('default').filter(q_filter))

    ql = q.lower()

    def score(m):
        topic = (m.topic or '').lower()
        chapter = (m.chapter or '').lower()
        subj = ((m.subject_name or m.subject_tr) or '').lower()
        s = 0.0
        if topic == ql:
            s += 1000
        if topic.startswith(ql):
            s += 500
        if ql in topic:
            s += 200
        if ql in chapter:
            s += 80
        if ql in subj:
            s += 60
        s += sum(2 for t in tokens if t.lower() in topic)
        s += sum(1 for t in tokens if t.lower() in chapter)
        s += min(m.question_count or 0, 1000) * 0.001
        return s

    matches.sort(key=score, reverse=True)
    return matches[:limit]


def related_topics(match, limit=6):
    """Topics related to a matched row (same subject or chapter)."""
    from .models import TutorTopicIndex

    if match is None:
        return []
    qs = TutorTopicIndex.objects.using('default').exclude(fingerprint=match.fingerprint)
    q_filter = Q()
    if match.subject_tr:
        q_filter |= Q(subject_tr=match.subject_tr)
    if match.chapter:
        q_filter |= Q(chapter=match.chapter)
    if not q_filter:
        q_filter = Q(table_name=match.table_name)
    return list(qs.filter(q_filter).order_by('-question_count')[:limit])


def popular_topics(limit=8):
    from .models import TutorTopicIndex

    return list(TutorTopicIndex.objects.using('default').order_by('-question_count')[:limit])


def sample_questions(match, limit=4):
    """A few real questions for a matched topic (raw SQL on the source table)."""
    if match is None:
        return []
    alias = match.db_alias
    if alias not in connections:
        return []
    conn = connections[alias]
    table_name = match.table_name
    cols = _table_columns(conn, table_name)
    select_cols = [
        'qid', 'subject', 'chapter', 'topic', 'question',
        'option_1', 'option_2', 'option_3', 'option_4', 'answer', 'explanation',
    ]
    select_cols = [c for c in select_cols if c in cols]
    if not select_cols:
        return []
    pk = select_cols[0]
    sql = 'SELECT {} FROM `{}` WHERE chapter = %s AND topic = %s ORDER BY `{}` LIMIT %s'.format(
        ', '.join('`{}`'.format(c) for c in select_cols), table_name, pk
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql, [match.chapter or '', match.topic or '', limit])
            rows = cur.fetchall()
    except Exception as e:
        logger.warning('sample_questions: %s', e)
        return []
    out = []
    for row in rows:
        rec = {}
        for k, v in zip(select_cols, row):
            rec[k] = (v or '').strip() if isinstance(v, str) else v
        out.append(rec)
    return out


def serialize_index_row(m):
    return {
        'fingerprint': m.fingerprint,
        'db_alias': m.db_alias,
        'table_name': m.table_name,
        'level_tr': m.level_tr,
        'class_level': m.class_level,
        'subject_tr': m.subject_tr,
        'subject_name': m.subject_name,
        'chapter_no': m.chapter_no,
        'chapter': m.chapter,
        'topic_no': m.topic_no,
        'topic': m.topic,
        'question_count': m.question_count,
    }

