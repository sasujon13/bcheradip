"""
Exam creation actions called from admin Settings: Create Exam and Add Exam.
Uses filters (level_tr, class_level, subject_tr, chapter, topic) and db_alias.
Stores exam sets in cheradip_exam_set; optionally summary in cheradip_subject.ChapterQ/SubjectQ.
Created exams are listed at /student/regularexam.
"""
import json
import logging
import random
from datetime import timedelta

from django.conf import settings
from django.db import connections
from django.utils import timezone

from .ai_question_generator import generate_questions_from_ai
from .subject_question_tables import next_qid_for_chapter_topic, subject_question_table_name

logger = logging.getLogger(__name__)


EXAM_SET_EXTRA_COLUMNS = {
    'exam_mode': "VARCHAR(16) NOT NULL DEFAULT 'regular'",
    'exam_variant': "VARCHAR(32) NULL",
    'duration_minutes': "INT NOT NULL DEFAULT 20",
    'question_count': "INT NOT NULL DEFAULT 30",
    'available_from': "DATETIME(6) NULL",
    'available_until': "DATETIME(6) NULL",
}


def _ensure_exam_set_schema(cursor):
    """Upgrade older raw exam-set tables without requiring a Django model migration."""
    for column, definition in EXAM_SET_EXTRA_COLUMNS.items():
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() "
            "AND table_name = 'cheradip_exam_set' AND column_name = %s",
            [column],
        )
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE cheradip_exam_set ADD COLUMN %s %s" % (column, definition))
    cursor.execute(
        "UPDATE cheradip_exam_set SET exam_mode = 'regular' "
        "WHERE exam_mode IS NULL OR TRIM(exam_mode) = ''"
    )


# Question tables and exam_set live in hsc (or honours); use hsc when db_alias is default/hsc
def _exam_db_alias(db_alias):
    if db_alias in ('hsc', 'honours'):
        return db_alias
    return 'hsc'


def _parse_groups_column(raw):
    """Parse groups column (JSON array or comma-separated)."""
    if not raw or not (raw := str(raw).strip()):
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
        if isinstance(parsed, str):
            return [p.strip() for p in parsed.replace('，', ',').split(',') if p.strip()]
        return []
    except (TypeError, ValueError, json.JSONDecodeError):
        return [p.strip() for p in raw.replace('，', ',').split(',') if p.strip()]


# Delimiter for topic/chapter lists in form POST (topic/chapter names may contain commas)
TOPIC_CHAPTER_DELIM = '\u241F'

def _parse_comma_list(value):
    """Return list of non-empty stripped strings from comma-separated value."""
    if not value or not (value := (value or '').strip()):
        return []
    return [s.strip() for s in value.split(',') if s.strip()]


def _parse_topic_chapter_list(value):
    """Return list of non-empty stripped strings. Uses UNIT SEPARATOR (U+241F) if present, else comma (so topic/chapter names can contain commas)."""
    if not value or not (value := (value or '').strip()):
        return []
    delim = TOPIC_CHAPTER_DELIM if TOPIC_CHAPTER_DELIM in value else ','
    return [s.strip() for s in value.split(delim) if s.strip()]


def _get_subject_scope(conn, filters):
    """Return list of (level_tr, class_level, subject_tr, sq) for which we have a subject question table.
    Accepts comma-separated level_tr, class_level, subject_tr; optional group (filter by groups column).
    """
    levels = _parse_comma_list(filters.get('level_tr'))
    classes = _parse_comma_list(filters.get('class_level'))
    subjects = _parse_comma_list(filters.get('subject_tr'))
    groups = _parse_comma_list(filters.get('group'))
    scope = []
    with conn.cursor() as cur:
        if levels and classes and subjects:
            for lt in levels:
                for cl in classes:
                    for st in subjects:
                        cur.execute(
                            "SELECT level_tr, class_level, subject_tr, COALESCE(sq, 30) FROM cheradip_subject "
                            "WHERE level_tr = %s AND class_level = %s AND subject_tr = %s LIMIT 1",
                            [lt, cl, st]
                        )
                        row = cur.fetchone()
                        if row:
                            scope.append((row[0], row[1], row[2], int(row[3] or 30)))
        else:
            sql = (
                "SELECT level_tr, class_level, subject_tr, COALESCE(MAX(sq), 30) FROM cheradip_subject "
                "WHERE subject_tr IS NOT NULL AND TRIM(COALESCE(subject_tr, '')) != '' "
            )
            params = []
            if levels:
                sql += " AND level_tr IN (" + ",".join(["%s"] * len(levels)) + ") "
                params.extend(levels)
            if classes:
                sql += " AND class_level IN (" + ",".join(["%s"] * len(classes)) + ") "
                params.extend(classes)
            if subjects:
                sql += " AND subject_tr IN (" + ",".join(["%s"] * len(subjects)) + ") "
                params.extend(subjects)
            if groups:
                sql += " AND (groups IS NOT NULL AND TRIM(COALESCE(groups, '')) != '') "
            sql += " GROUP BY level_tr, class_level, subject_tr ORDER BY level_tr, class_level, subject_tr "
            cur.execute(sql, params)
            for row in cur.fetchall() or []:
                scope.append((row[0], row[1], row[2], int(row[3] or 30)))
            if groups and scope:
                cur.execute("SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject' AND column_name = 'groups'")
                if cur.fetchone():
                    filtered = []
                    for row in scope:
                        cur.execute("SELECT groups FROM cheradip_subject WHERE level_tr = %s AND class_level = %s AND subject_tr = %s LIMIT 1", [row[0], row[1], row[2]])
                        r = cur.fetchone()
                        if r and r[0]:
                            subj_groups = _parse_groups_column(r[0])
                            if any(g in subj_groups for g in groups):
                                filtered.append(row)
                        else:
                            filtered.append(row)
                    scope = filtered
    return scope


def _table_exists(cursor, table_name):
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
        [table_name]
    )
    return cursor.fetchone() is not None


def _chapter_name(cursor, tbl, ch_no):
    """Best-effort chapter display name for a chapter_no."""
    try:
        cursor.execute(
            "SELECT chapter FROM `%s` WHERE chapter_no = %%s AND chapter IS NOT NULL "
            "AND TRIM(COALESCE(chapter, '')) != '' LIMIT 1" % tbl,
            [ch_no],
        )
        row = cursor.fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    return None


def _norm_text(s):
    """Normalize question/answer text for uniqueness comparison."""
    import re as _re
    return _re.sub(r"\s+", "", str(s or "").strip().lower())


def _mcq_condition(cursor, tbl):
    """Return a SQL condition restricting to MCQ questions, or '' when the
    subject table has no `type` column (e.g. honours/job tables where every
    row is already a question row).

    Values seen in HSC tables: 'বহুনির্বাচনি প্রশ্ন' (MCQ), 'সৃজনশীল প্রশ্ন' (CQ),
    'জ্ঞানমূলক প্রশ্ন' (knowledge), 'অনুধাবনমূলক প্রশ্ন' (comprehension).
    """
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = 'type'",
            [tbl],
        )
        if cursor.fetchone()[0]:
            # MySQL interpolates %s parameters after this fragment is composed.
            # Escape LIKE wildcards for that pass; without params, doubled
            # wildcards have the same SQL matching behavior as a single %.
            return "type LIKE '%%বহুনির্বাচনি%%'"
    except Exception:
        pass
    return ''


def _emit(progress, **kw):
    """Call the progress callback without letting a UI bug break the job."""
    if progress:
        try:
            progress(**kw)
        except Exception:
            pass


def _count_ai_rows(cur, tbl):
    """Existing AI-created question rows (updated_by='Cheradip AI') in a subject table."""
    try:
        cur.execute("SELECT COUNT(*) FROM `%s` WHERE updated_by = 'Cheradip AI'" % tbl.replace('`', '``'))
        return int(cur.fetchone()[0] or 0)
    except Exception:
        return 0


def _remove_non_mcq_rows(cur, table_name, mcq_cond):
    """Delete question rows that are NOT MCQ (only when the table has a `type` column).

    Keeps only explicit 'বহুনির্বাচনি*' rows so exam sets are built from MCQ questions only.
    Returns the number of removed rows.
    """
    if not mcq_cond:
        return 0
    tbl = table_name.replace('`', '``')
    try:
        cur.execute(
            "DELETE FROM `%s` WHERE type IS NULL OR TRIM(COALESCE(type, '')) = '' OR NOT %s" % (tbl, mcq_cond)
        )
        return max(0, int(cur.rowcount or 0))
    except Exception:
        return 0


def _fetch_topic_rows(cursor, tbl, ch_no, topic_name):
    """Return list of dicts {qid, question, answer} for a topic (MCQ only where a type column exists)."""
    mcq = _mcq_condition(cursor, tbl)
    try:
        cursor.execute(
            "SELECT qid, question, answer FROM `%s` WHERE (chapter_no = %%s OR chapter = %%s) AND topic = %%s "
            "%s AND question IS NOT NULL AND TRIM(COALESCE(question, '')) != '' ORDER BY qid" % (tbl, ("AND " + mcq if mcq else "")),
            [ch_no, ch_no, topic_name],
        )
        return [{"qid": r[0], "question": r[1], "answer": r[2]} for r in cursor.fetchall()]
    except Exception:
        return []


def _dedupe_rows(rows):
    """Keep rows with unique question text AND unique answer (first occurrence wins)."""
    seen_q = set()
    seen_a = set()
    out = []
    for row in rows:
        qn = _norm_text(row.get("question"))
        an = _norm_text(row.get("answer"))
        if not qn or not an:
            continue
        if qn in seen_q or an in seen_a:
            continue
        seen_q.add(qn)
        seen_a.add(an)
        out.append(row)
    return out


def _ai_fill_topic_qids(cursor, alias, table_name, level_tr, class_level, subject_tr,
                        ch_no, topic_no, topic_name, sq, all_qids):
    """Return `sq` unique qids for a topic, creating missing questions via AI.

    Questions and answers are kept unique — both among the topic's existing rows
    and among the AI-generated ones. When the topic cannot supply `sq` unique
    questions (even after asking Cloud AI first, then Home AI), this returns None so
    the caller SKIPS the set, rather than placing duplicate questions/answers.
    """
    tbl = table_name.replace('`', '``')
    rows = _dedupe_rows(_fetch_topic_rows(cursor, tbl, ch_no, topic_name))
    base_qids = [r["qid"] for r in rows]
    qids = list(base_qids)
    if len(qids) >= sq:
        random.shuffle(qids)
        return (qids[:sq], 0)

    if getattr(settings, 'EXAM_AI_FILL_ENABLED', True):
        try:
            ch_name = _chapter_name(cursor, tbl, ch_no)
            samples = [r.get('question') for r in rows[:8]]
            now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            questions, provider = generate_questions_from_ai(
                subject_tr=subject_tr,
                level_tr=level_tr,
                class_level=class_level,
                chapter_no=ch_no,
                chapter=ch_name,
                topic_no=topic_no,
                topic=topic_name,
                count=sq - len(qids),
                sample_questions=samples,
                existing_questions=[
                    {'question': r.get('question'), 'answer': r.get('answer')} for r in rows
                ],
            )
            for q in questions:
                qid = next_qid_for_chapter_topic(table_name, (ch_no or '0'), (topic_no or '0'), using=alias)
                cursor.execute(
                    "INSERT INTO `%s` (qid, subject, chapter_no, chapter, topic_no, topic, question, option_1, "
                    "option_2, option_3, option_4, answer, explanation, explanation2, explanation3, type, level, "
                    "subsource, created_at, updated_at, updated_by) "
                    "VALUES (%%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s)" % tbl,
                    [
                        qid, subject_tr, ch_no or None, ch_name or None, topic_no or None, topic_name or None,
                        q['question'], q.get('option_1') or '', q.get('option_2') or '', q.get('option_3') or '',
                        q.get('option_4') or '', q['answer'], q.get('explanation') or '',
                        q.get('explanation2') or None, q.get('explanation3') or None,
                        'বহুনির্বাচনি প্রশ্ন', level_tr or None, None, now, now, 'Cheradip AI',
                    ],
                )
                qids.append(qid)
                if len(qids) >= sq:
                    break
        except Exception as e:
            logger.warning('AI question fill failed for %s / %s / %s (topic=%s): %s',
                           level_tr, class_level, subject_tr, topic_name, e)

    random.shuffle(qids)
    if len(qids) >= sq:
        ai_created = len(qids) - len(base_qids)
        return (qids[:sq], ai_created)
    return None  # SKIP: cannot build a set of sq unique questions/answers


def _create_topic_sets(cursor, table_name, level_tr, class_level, subject_tr, sq, db_alias, chapter_list, topic_list, skipped=None, progress=None, ai_stats=None):
    """Create topic-based exam sets: chapter_no.topic_no: Topic Name (e.g. 1.1: All Topics), ordered by chapter_no then topic_no."""
    tbl = table_name.replace('`', '``')
    mcq = _mcq_condition(cursor, tbl)  # MCQ-only filter when the table has a type column
    # Build list of (chapter_no, topic_no, topic_name) ordered by chapter_no, topic_no (numeric)
    order_sql = "ORDER BY CAST(COALESCE(NULLIF(TRIM(chapter_no), ''), '0') AS UNSIGNED), CAST(COALESCE(NULLIF(TRIM(topic_no), ''), '0') AS UNSIGNED), topic"
    if chapter_list:
        placeholders = ', '.join(['%s'] * len(chapter_list))
        cursor.execute(
            "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE (chapter_no IN (" + placeholders + ") OR chapter IN (" + placeholders + ")) "
            "AND topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + ("AND " + mcq if mcq else "") + order_sql,
            list(chapter_list) + list(chapter_list)
        )
        topics = cursor.fetchall() or []
    else:
        cursor.execute(
            "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + ("AND " + mcq if mcq else "") + order_sql
        )
        topics = cursor.fetchall() or []
    # If user selected specific topics, keep only those (match by topic name); keep one row per (chapter_no, topic_no, topic)
    if topic_list:
        topic_set = {s.strip() for s in topic_list if s and str(s).strip()}
        topics = [
            (t[0], t[1], t[2]) for t in topics
            if (t[2] or '').strip() in topic_set or (t[1] is not None and str(t[1]).strip() in topic_set)
        ]
    now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    created = 0
    total = len(topics)
    if ai_stats is not None:
        ai_stats.setdefault('total', 0)
    for idx, (ch_no, topic_no, topic_name) in enumerate(topics):
        tname = (topic_name or '').strip() or ('Topic %s' % (topic_no or ''))
        ch_no_s = (ch_no or '').strip() or '0'
        topic_no_s = (topic_no or '').strip() or '0'
        _emit(progress,
              phase='Topic sets',
              current_subject=subject_tr,
              current_chapter=ch_no_s,
              current_topic=tname,
              topics_done=idx,
              topics_total=total,
              ai_created_total=(ai_stats.get('total', 0) if ai_stats else 0),
              ai_created_current=0,
              percent=int(idx * 100 / total) if total else 0)
        cursor.execute(
            "SELECT qid FROM `" + tbl + "` WHERE (chapter_no = %s OR chapter = %s) AND topic = %s " + ("AND " + mcq if mcq else "") + " ORDER BY RAND()",
            [ch_no, ch_no, topic_name]
        )
        all_qids = [r[0] for r in cursor.fetchall()]
        if not all_qids:
            continue
        qids = _ai_fill_topic_qids(
            cursor, db_alias, table_name, level_tr, class_level, subject_tr,
            ch_no, topic_no, topic_name, sq, all_qids,
        )
        if qids is None:
            if skipped is not None:
                skipped.append("%s.%s: %s" % (ch_no_s, topic_no_s, tname))
            continue
        qids, ai_created = qids
        if ai_stats is not None:
            ai_stats['total'] = ai_stats.get('total', 0) + ai_created
        set_key = "%s.%s" % (ch_no_s, topic_no_s)
        name_label = "%s.%s: %s" % (ch_no_s, topic_no_s, tname)
        cursor.execute(
            "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'topic', %s, %s, %s, %s)",
            [db_alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(qids), now]
        )
        created += 1
        _emit(progress,
              phase='Topic sets',
              current_subject=subject_tr,
              current_chapter=ch_no_s,
              current_topic=tname,
              topics_done=idx + 1,
              topics_total=total,
              ai_created_total=(ai_stats.get('total', 0) if ai_stats else 0),
              ai_created_current=ai_created,
              percent=min(95, int((idx + 1) * 100 / total)) if total else 95)
    return created


def _create_chapter_sets(cursor, table_name, level_tr, class_level, subject_tr, sq, db_alias, chapter_list, progress=None, ai_stats=None):
    """Chapter-based: 0: Chapter name, 1: Chapter name, ... ; sq questions per set (never only 10)."""
    tbl = table_name.replace('`', '``')
    mcq = _mcq_condition(cursor, tbl)
    if chapter_list:
        placeholders = ', '.join(['%s'] * len(chapter_list))
        cursor.execute(
            "SELECT DISTINCT chapter_no, chapter FROM `" + tbl + "` WHERE (chapter_no IN (" + placeholders + ") OR chapter IN (" + placeholders + ")) " + ("AND " + mcq if mcq else "") + " ORDER BY chapter_no, chapter",
            list(chapter_list) + list(chapter_list)
        )
    else:
        cursor.execute(
            "SELECT DISTINCT chapter_no, chapter FROM `" + tbl + "` WHERE ((chapter_no IS NOT NULL AND TRIM(COALESCE(chapter_no, '')) != '') OR (chapter IS NOT NULL AND TRIM(COALESCE(chapter, '')) != '')) " + ("AND " + mcq if mcq else "") + " ORDER BY chapter_no, chapter"
        )
    chapters = cursor.fetchall() or []
    now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    set_index = 0
    for ch_no, ch_name in chapters:
        cname = (ch_name or '').strip() or ('Chapter %s' % (ch_no or ''))
        cursor.execute(
            "SELECT qid FROM `" + tbl + "` WHERE (chapter_no = %s OR chapter = %s) " + ("AND " + mcq if mcq else "") + " ORDER BY RAND()",
            [ch_no, ch_name]
        )
        all_qids = [r[0] for r in cursor.fetchall()]
        if not all_qids:
            continue
        random.shuffle(all_qids)
        # sq questions per set (same as cheradip_subject.sq); never only 10.
        # Only full sets are created so every set has exactly sq questions;
        # any small leftover is still covered by the topic-based sets.
        n_full = len(all_qids) // sq
        for s in range(n_full):
            chunk = all_qids[s * sq:(s + 1) * sq]
            set_key = str(set_index)
            name_label = "%s: %s" % (set_key, cname)
            cursor.execute(
                "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'chapter', %s, %s, %s, %s)",
                [db_alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(chunk), now]
            )
            set_index += 1
    _emit(progress,
          phase='Chapter sets',
          current_subject=subject_tr,
          current_chapter='',
          current_topic='',
          topics_done=0,
          topics_total=0,
          ai_created_total=(ai_stats.get('total', 0) if ai_stats else 0),
          ai_created_current=0,
          percent=96)
    return set_index


def _create_subject_sets(cursor, table_name, level_tr, class_level, subject_tr, sq, db_alias, progress=None, ai_stats=None):
    """Subject-based: 0.01 Subject name, 0.02, ... 0.99; order questions (999 order), sq per set, max 99 sets."""
    tbl = table_name.replace('`', '``')
    mcq = _mcq_condition(cursor, tbl)
    cursor.execute(
        "SELECT qid FROM `" + tbl + "` " + ("WHERE " + mcq if mcq else "") + " ORDER BY COALESCE(NULLIF(TRIM(chapter_no), ''), '0'), COALESCE(NULLIF(TRIM(topic_no), ''), '0'), qid LIMIT 999"
    )
    ordered_qids = [r[0] for r in cursor.fetchall()]
    if not ordered_qids:
        return 0
    now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    per_set = sq or 30
    count = 0
    # Only full sets of sq questions (never a small remainder set).
    for i in range(1, 100):
        start = (i - 1) * per_set
        chunk = ordered_qids[start:start + per_set]
        if len(chunk) < per_set:
            break
        set_key = "0.%02d" % i
        name_label = "%s %s" % (set_key, subject_tr or 'Subject')
        cursor.execute(
            "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'subject', %s, %s, %s, %s)",
            [db_alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(chunk), now]
        )
        count += 1
    _emit(progress,
          phase='Subject sets',
          current_subject=subject_tr,
          current_chapter='',
          current_topic='',
          topics_done=0,
          topics_total=0,
          ai_created_total=(ai_stats.get('total', 0) if ai_stats else 0),
          ai_created_current=0,
          percent=98)
    return count


def _selected_question_qids(cursor, table_name, chapter_list=None, topic_list=None):
    """Return unique MCQ ids from the selected curriculum scope in random order."""
    tbl = table_name.replace('`', '``')
    conditions = []
    params = []
    mcq = _mcq_condition(cursor, tbl)
    if mcq:
        conditions.append(mcq)
    if chapter_list:
        placeholders = ', '.join(['%s'] * len(chapter_list))
        conditions.append("(chapter_no IN (%s) OR chapter IN (%s))" % (placeholders, placeholders))
        params.extend(chapter_list)
        params.extend(chapter_list)
    if topic_list:
        placeholders = ', '.join(['%s'] * len(topic_list))
        conditions.append("(topic_no IN (%s) OR topic IN (%s))" % (placeholders, placeholders))
        params.extend(topic_list)
        params.extend(topic_list)
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    cursor.execute("SELECT qid FROM `%s`%s ORDER BY RAND()" % (tbl, where), params or None)
    seen = set()
    qids = []
    for row in cursor.fetchall() or []:
        qid = row[0]
        key = str(qid)
        if qid is not None and key not in seen:
            seen.add(key)
            qids.append(qid)
    return qids


def _selected_question_rows(cursor, table_name, chapter_list=None, topic_list=None):
    """Load and deduplicate the selected MCQ pool by both question and answer."""
    tbl = table_name.replace('`', '``')
    conditions = ["question IS NOT NULL", "TRIM(COALESCE(question, '')) != ''"]
    params = []
    mcq = _mcq_condition(cursor, tbl)
    if mcq:
        conditions.append(mcq)
    if chapter_list:
        placeholders = ', '.join(['%s'] * len(chapter_list))
        conditions.append("(chapter_no IN (%s) OR chapter IN (%s))" % (placeholders, placeholders))
        params.extend(chapter_list)
        params.extend(chapter_list)
    if topic_list:
        placeholders = ', '.join(['%s'] * len(topic_list))
        conditions.append("(topic_no IN (%s) OR topic IN (%s))" % (placeholders, placeholders))
        params.extend(topic_list)
        params.extend(topic_list)
    cursor.execute(
        "SELECT qid, question, answer, chapter_no, chapter, topic_no, topic FROM `%s` "
        "WHERE %s ORDER BY RAND()" % (tbl, ' AND '.join(conditions)),
        params or None,
    )
    rows = [
        {
            'qid': row[0], 'question': row[1], 'answer': row[2],
            'chapter_no': row[3], 'chapter': row[4],
            'topic_no': row[5], 'topic': row[6],
        }
        for row in (cursor.fetchall() or [])
    ]
    return _dedupe_rows(rows)


def _fill_practice_question_qids(cursor, alias, table_name, level_tr, class_level,
                                  subject_tr, chapter_list, topic_list, target=100):
    """Return up to ``target`` unique MCQs, persisting validated AI questions when needed."""
    rows = _selected_question_rows(cursor, table_name, chapter_list, topic_list)
    random.shuffle(rows)
    if len(rows) >= target:
        return [row['qid'] for row in rows[:target]], 0
    if not getattr(settings, 'EXAM_AI_FILL_ENABLED', True):
        return [row['qid'] for row in rows], 0

    first = rows[0] if rows else {}
    ch_no = first.get('chapter_no') or (chapter_list[0] if chapter_list else '0')
    chapter = first.get('chapter') or (chapter_list[0] if chapter_list else 'AI Practice')
    topic_no = first.get('topic_no') or (topic_list[0] if topic_list else '0')
    topic = first.get('topic') or (topic_list[0] if topic_list else 'AI Practice')
    tbl = table_name.replace('`', '``')
    created = 0
    # Smaller batches produce more reliable structured JSON than one 100-question response.
    while len(rows) < target:
        missing = target - len(rows)
        batch_size = min(10, missing)
        try:
            questions, _provider = generate_questions_from_ai(
                subject_tr=subject_tr,
                level_tr=level_tr,
                class_level=class_level,
                chapter_no=ch_no,
                chapter=chapter,
                topic_no=topic_no,
                topic=topic,
                count=batch_size,
                sample_questions=[row.get('question') for row in rows[:8]],
                existing_questions=[
                    {'question': row.get('question'), 'answer': row.get('answer')}
                    for row in rows
                ],
            )
        except Exception as exc:
            logger.warning('Practice AI fill failed for %s / %s: %s', subject_tr, topic, exc)
            break
        if not questions:
            break
        inserted_this_batch = 0
        now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        for question in questions:
            qid = next_qid_for_chapter_topic(
                table_name, str(ch_no or '0'), str(topic_no or '0'), using=alias
            )
            cursor.execute(
                "INSERT INTO `%s` (qid, subject, chapter_no, chapter, topic_no, topic, question, option_1, "
                "option_2, option_3, option_4, answer, explanation, explanation2, explanation3, type, level, "
                "subsource, created_at, updated_at, updated_by) "
                "VALUES (%%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s)" % tbl,
                [
                    qid, subject_tr, ch_no or None, chapter or None, topic_no or None, topic or None,
                    question['question'], question.get('option_1') or '', question.get('option_2') or '',
                    question.get('option_3') or '', question.get('option_4') or '', question['answer'],
                    question.get('explanation') or '', question.get('explanation2') or None,
                    question.get('explanation3') or None, 'বহুনির্বাচনি প্রশ্ন', level_tr or None, None,
                    now, now, 'Cheradip AI',
                ],
            )
            rows.append({
                'qid': qid,
                'question': question['question'],
                'answer': question['answer'],
                'chapter_no': ch_no, 'chapter': chapter,
                'topic_no': topic_no, 'topic': topic,
            })
            created += 1
            inserted_this_batch += 1
            if len(rows) >= target:
                break
        if inserted_this_batch == 0:
            break
    random.shuffle(rows)
    return [row['qid'] for row in rows[:target]], created


def _scope_exam_type(chapter_list, topic_list):
    if topic_list:
        return 'topic'
    if chapter_list:
        return 'chapter'
    return 'subject'


def _run_live_exam(db_alias, filters, progress=None, replace=False):
    """Create live papers, optionally replacing all previous live papers in scope."""
    alias = _exam_db_alias(db_alias)
    if alias not in connections:
        return {'message': 'Database not configured.'}
    conn = connections[alias]
    scope = _get_subject_scope(conn, filters)
    if not scope:
        return {'message': 'No subjects found for the selected filters.'}
    chapter_list = _parse_topic_chapter_list(filters.get('chapter'))
    topic_list = _parse_topic_chapter_list(filters.get('topic'))
    created = skipped = existing = 0
    now = timezone.now()
    try:
        with conn.cursor() as cur:
            _ensure_exam_set_schema(cur)
            for index, (level_tr, class_level, subject_tr, sq) in enumerate(scope):
                table_name = subject_question_table_name(level_tr, class_level, subject_tr)
                if not _table_exists(cur, table_name):
                    skipped += 1
                    continue
                _emit(progress, phase='Live exam', current_subject=subject_tr,
                      current_chapter='', current_topic='', percent=int(index * 100 / len(scope)))
                exam_type = _scope_exam_type(chapter_list, topic_list)
                if not replace:
                    cur.execute(
                        "SELECT COUNT(*) FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s "
                        "AND class_level = %s AND subject_tr = %s AND exam_mode = 'live' "
                        "AND exam_type = %s AND (available_until IS NULL OR available_until >= %s)",
                        [alias, level_tr, class_level, subject_tr, exam_type, now],
                    )
                    if int(cur.fetchone()[0] or 0) > 0:
                        existing += 1
                        continue
                qids = _selected_question_qids(cur, table_name, chapter_list, topic_list)
                target = max(1, min(int(sq or 30), 50))
                if len(qids) < target:
                    skipped += 1
                    continue
                duration = max(20, target)
                available_until = now + timedelta(minutes=duration + 15)
                if replace:
                    cur.execute(
                        "DELETE FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s "
                        "AND class_level = %s AND subject_tr = %s AND exam_mode = 'live'",
                        [alias, level_tr, class_level, subject_tr],
                    )
                stamp = now.strftime('%Y%m%d%H%M%S')
                name = "Live Exam - %s (%d Questions)" % (subject_tr, target)
                cur.execute(
                    "INSERT INTO cheradip_exam_set "
                    "(db_alias, level_tr, class_level, subject_tr, exam_type, exam_mode, exam_variant, "
                    "set_key, name_label, qids_json, duration_minutes, question_count, available_from, "
                    "available_until, created_at) VALUES (%s, %s, %s, %s, %s, 'live', 'timed', %s, %s, %s, %s, %s, %s, %s, %s)",
                    [alias, level_tr, class_level, subject_tr, exam_type,
                     'live-' + exam_type + '-' + stamp, name, json.dumps(qids[:target]), duration, target,
                     now, available_until, now],
                )
                created += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    action = 'Create Live Exam' if replace else 'Add Live Exam'
    return {'message': '%s: created %d fresh timed paper(s); kept %d subject(s) with an active live paper; skipped %d subject(s) without enough unique MCQs.' % (action, created, existing, skipped)}


def run_create_live_exam(db_alias, filters, progress=None):
    """Replace each selected subject's live paper with one fresh timed mixed paper."""
    return _run_live_exam(db_alias, filters, progress=progress, replace=True)


def run_add_live_exam(db_alias, filters, progress=None):
    """Add a live paper only where no active live paper already exists."""
    return _run_live_exam(db_alias, filters, progress=progress, replace=False)


def _run_practice_exam(db_alias, filters, progress=None, replace=False):
    """Create practice tiers, optionally replacing existing tiers in scope."""
    alias = _exam_db_alias(db_alias)
    if alias not in connections:
        return {'message': 'Database not configured.'}
    conn = connections[alias]
    scope = _get_subject_scope(conn, filters)
    if not scope:
        return {'message': 'No subjects found for the selected filters.'}
    chapter_list = _parse_topic_chapter_list(filters.get('chapter'))
    topic_list = _parse_topic_chapter_list(filters.get('topic'))
    tiers = (('short', 'Short', 25, 20), ('middle', 'Middle', 50, 40), ('hard', 'Hard', 100, 80))
    created = skipped = ai_created = existing = 0
    now = timezone.now()
    try:
        with conn.cursor() as cur:
            _ensure_exam_set_schema(cur)
            for index, (level_tr, class_level, subject_tr, _sq) in enumerate(scope):
                table_name = subject_question_table_name(level_tr, class_level, subject_tr)
                if not _table_exists(cur, table_name):
                    skipped += len(tiers)
                    continue
                _emit(progress, phase='Practice exams', current_subject=subject_tr,
                      current_chapter='', current_topic='', percent=int(index * 100 / len(scope)))
                exam_type = _scope_exam_type(chapter_list, topic_list)
                if replace:
                    missing_tiers = list(tiers)
                else:
                    cur.execute(
                        "SELECT exam_variant FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s "
                        "AND class_level = %s AND subject_tr = %s AND exam_mode = 'practice' AND exam_type = %s",
                        [alias, level_tr, class_level, subject_tr, exam_type],
                    )
                    existing_variants = {str(row[0] or '').strip() for row in (cur.fetchall() or [])}
                    missing_tiers = [tier for tier in tiers if tier[0] not in existing_variants]
                    existing += len(tiers) - len(missing_tiers)
                    if not missing_tiers:
                        continue
                target = max(tier[2] for tier in missing_tiers)
                qids, generated = _fill_practice_question_qids(
                    cur, alias, table_name, level_tr, class_level, subject_tr,
                    chapter_list, topic_list, target=target,
                )
                ai_created += generated
                _emit(progress, phase='Practice exams', current_subject=subject_tr,
                      current_chapter='', current_topic='', ai_created_total=ai_created,
                      ai_created_current=generated,
                      percent=min(95, int((index + 1) * 100 / len(scope))))
                if replace:
                    cur.execute(
                        "DELETE FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s "
                        "AND class_level = %s AND subject_tr = %s AND exam_mode = 'practice'",
                        [alias, level_tr, class_level, subject_tr],
                    )
                for variant, label, count, duration in missing_tiers:
                    if len(qids) < count:
                        skipped += 1
                        continue
                    chosen = random.sample(qids, count)
                    name = "%s Practice Exam - %s (%d Questions)" % (label, subject_tr, count)
                    cur.execute(
                        "INSERT INTO cheradip_exam_set "
                        "(db_alias, level_tr, class_level, subject_tr, exam_type, exam_mode, exam_variant, "
                        "set_key, name_label, qids_json, duration_minutes, question_count, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, 'practice', %s, %s, %s, %s, %s, %s, %s)",
                        [alias, level_tr, class_level, subject_tr, exam_type, variant,
                         'practice-' + exam_type + '-' + variant, name, json.dumps(chosen), duration, count, now],
                    )
                    created += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    action = 'Create Practice Exam' if replace else 'Add Practice Exam'
    return {'message': '%s: created %d Short/Middle/Hard paper(s), kept %d existing tier(s), and added %d AI-created MCQ(s); skipped %d tier(s) because enough valid unique MCQs could not be produced.' % (action, created, existing, ai_created, skipped)}


def run_create_practice_exam(db_alias, filters, progress=None):
    """Replace selected practice tiers with fresh Short/Middle/Hard papers."""
    return _run_practice_exam(db_alias, filters, progress=progress, replace=True)


def run_add_practice_exam(db_alias, filters, progress=None):
    """Add only missing Short/Middle/Hard practice tiers."""
    return _run_practice_exam(db_alias, filters, progress=progress, replace=False)


def run_create_exam(db_alias, filters, progress=None):
    """
    Create or recreate exam question sets for the given filters.
    If all filters are "All", create/update for all subjects that have questions.
    """
    alias = _exam_db_alias(db_alias)
    if alias not in connections:
        return {'message': 'Database not configured.'}
    conn = connections[alias]
    scope = _get_subject_scope(conn, filters)
    if not scope:
        return {'message': 'No subjects found for the selected filters.'}
    chapter_list = _parse_topic_chapter_list(filters.get('chapter'))
    topic_list = _parse_topic_chapter_list(filters.get('topic'))
    created_topic, created_chapter, created_subject = 0, 0, 0
    skipped = []
    ai_stats = {'total': 0}
    removed_non_mcq = 0
    try:
        with conn.cursor() as cur:
            _ensure_exam_set_schema(cur)
            for level_tr, class_level, subject_tr, sq in scope:
                table_name = subject_question_table_name(level_tr, class_level, subject_tr)
                if not _table_exists(cur, table_name):
                    continue
                # MCQ-only: remove any non-MCQ rows from the subject table first
                removed_non_mcq += _remove_non_mcq_rows(cur, table_name, _mcq_condition(cur, table_name))
                # Report the subject being processed + existing AI-created questions
                _emit(progress,
                      phase='Preparing',
                      current_subject=subject_tr,
                      current_chapter='',
                      current_topic='',
                      ai_existing=_count_ai_rows(cur, table_name),
                      ai_created_total=ai_stats.get('total', 0),
                      ai_created_current=0,
                      percent=0)
                # Delete existing exam sets for this subject (recreate)
                cur.execute(
                    "DELETE FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_mode = 'regular'",
                    [alias, level_tr, class_level, subject_tr]
                )
                created_topic += _create_topic_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, chapter_list, topic_list, skipped=skipped, progress=progress, ai_stats=ai_stats)
                created_chapter += _create_chapter_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, chapter_list, progress=progress, ai_stats=ai_stats)
                created_subject += _create_subject_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, progress=progress, ai_stats=ai_stats)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    msg = 'Created exam sets: %d topic, %d chapter, %d subject.' % (created_topic, created_chapter, created_subject)
    if removed_non_mcq:
        msg += ' Removed %d non-MCQ question row(s).' % removed_non_mcq
    if skipped:
        msg += ' Skipped (could not build %d unique-question topic set(s) via Home/Cloud AI): %s' % (
            len(skipped), ', '.join(skipped))
    return {'message': msg}


def run_add_exam(db_alias, filters, progress=None):
    """
    Create only missing exam sets for the selected category (do not overwrite existing).
    """
    alias = _exam_db_alias(db_alias)
    if alias not in connections:
        return {'message': 'Database not configured.'}
    conn = connections[alias]
    scope = _get_subject_scope(conn, filters)
    if not scope:
        return {'message': 'No subjects found for the selected filters.'}
    chapter_list = _parse_topic_chapter_list(filters.get('chapter'))
    topic_list = _parse_topic_chapter_list(filters.get('topic'))
    added = 0
    skipped = []
    ai_stats = {'total': 0}
    removed_non_mcq = 0
    try:
        with conn.cursor() as cur:
            _ensure_exam_set_schema(cur)
            for level_tr, class_level, subject_tr, sq in scope:
                table_name = subject_question_table_name(level_tr, class_level, subject_tr)
                if not _table_exists(cur, table_name):
                    continue
                _emit(progress,
                      phase='Preparing',
                      current_subject=subject_tr,
                      current_chapter='',
                      current_topic='',
                      ai_existing=_count_ai_rows(cur, table_name),
                      ai_created_total=ai_stats.get('total', 0),
                      ai_created_current=0,
                      percent=0)
                # Topic: only add sets for topics that don't have an exam_set row
                cur.execute(
                    "SELECT set_key FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_mode = 'regular' AND exam_type = 'topic'",
                    [alias, level_tr, class_level, subject_tr]
                )
                existing_topic_keys = {r[0] for r in cur.fetchall()}
                tbl = table_name.replace('`', '``')
                mcq = _mcq_condition(cur, tbl)
                # MCQ-only: remove any non-MCQ rows so only MCQ questions remain
                removed_non_mcq += _remove_non_mcq_rows(cur, table_name, mcq)
                order_sql = "ORDER BY CAST(COALESCE(NULLIF(TRIM(chapter_no), ''), '0') AS UNSIGNED), CAST(COALESCE(NULLIF(TRIM(topic_no), ''), '0') AS UNSIGNED), topic"
                if chapter_list:
                    ph = ', '.join(['%s'] * len(chapter_list))
                    cur.execute(
                        "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE (chapter_no IN (" + ph + ") OR chapter IN (" + ph + ")) "
                        "AND topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + ("AND " + mcq if mcq else "") + order_sql,
                        list(chapter_list) + list(chapter_list)
                    )
                else:
                    cur.execute(
                        "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + ("AND " + mcq if mcq else "") + order_sql
                    )
                topics = cur.fetchall() or []
                if topic_list:
                    topic_set = {s.strip() for s in topic_list if s and str(s).strip()}
                    topics = [
                        t for t in topics
                        if (t[2] or '').strip() in topic_set or (t[1] is not None and str(t[1]).strip() in topic_set)
                    ]
                now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                topics_total = len(topics)
                for idx, (ch_no, topic_no, topic_name) in enumerate(topics):
                    ch_no_s = (ch_no or '').strip() or '0'
                    topic_no_s = (topic_no or '').strip() or '0'
                    set_key = "%s.%s" % (ch_no_s, topic_no_s)
                    tname = (topic_name or '').strip() or ('Topic %s' % (topic_no or ''))
                    _emit(progress,
                          phase='Topic sets',
                          current_subject=subject_tr,
                          current_chapter=ch_no_s,
                          current_topic=tname,
                          topics_done=idx,
                          topics_total=topics_total,
                          ai_created_total=ai_stats.get('total', 0),
                          ai_created_current=0,
                          percent=int(idx * 100 / topics_total) if topics_total else 0)
                    if set_key in existing_topic_keys:
                        continue
                    cur.execute(
                        "SELECT qid FROM `" + tbl + "` WHERE (chapter_no = %s OR chapter = %s) AND topic = %s " + ("AND " + mcq if mcq else "") + " ORDER BY RAND()",
                        [ch_no, ch_no, topic_name]
                    )
                    all_qids = [r[0] for r in cur.fetchall()]
                    if not all_qids:
                        continue
                    qids = _ai_fill_topic_qids(
                        cur, alias, table_name, level_tr, class_level, subject_tr,
                        ch_no, topic_no, topic_name, sq, all_qids,
                    )
                    if qids is None:
                        skipped.append("%s.%s: %s" % (ch_no_s, topic_no_s, tname))
                        continue
                    qids, ai_created = qids
                    ai_stats['total'] = ai_stats.get('total', 0) + ai_created
                    name_label = "%s.%s: %s" % (ch_no_s, topic_no_s, tname)
                    cur.execute(
                        "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'topic', %s, %s, %s, %s)",
                        [alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(qids), now]
                    )
                    added += 1
                    _emit(progress,
                          phase='Topic sets',
                          current_subject=subject_tr,
                          current_chapter=ch_no_s,
                          current_topic=tname,
                          topics_done=idx + 1,
                          topics_total=topics_total,
                          ai_created_total=ai_stats.get('total', 0),
                          ai_created_current=ai_created,
                          percent=min(95, int((idx + 1) * 100 / topics_total)) if topics_total else 95)
                # Chapter: check existing chapter set count; add if missing
                cur.execute(
                    "SELECT COUNT(*) FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_mode = 'regular' AND exam_type = 'chapter'",
                    [alias, level_tr, class_level, subject_tr]
                )
                if cur.fetchone()[0] == 0:
                    added += _create_chapter_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, chapter_list, progress=progress, ai_stats=ai_stats)
                # Subject: same
                cur.execute(
                    "SELECT COUNT(*) FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_mode = 'regular' AND exam_type = 'subject'",
                    [alias, level_tr, class_level, subject_tr]
                )
                if cur.fetchone()[0] == 0:
                    added += _create_subject_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, progress=progress, ai_stats=ai_stats)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    msg = 'Add Exam: added %d missing set(s).' % added
    if removed_non_mcq:
        msg += ' Removed %d non-MCQ question row(s) (MCQ-only).' % removed_non_mcq
    if skipped:
        msg += ' Skipped (could not build %d unique-question topic set(s) via Home/Cloud AI): %s' % (
            len(skipped), ', '.join(skipped))
    return {'message': msg}
