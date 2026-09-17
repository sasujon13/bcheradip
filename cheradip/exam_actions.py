"""
Exam creation actions called from admin Settings: Create Exam and Add Exam.
Uses filters (level_tr, class_level, subject_tr, chapter, topic) and db_alias.
Stores exam sets in cheradip_exam_set; optionally summary in cheradip_subject.ChapterQ/SubjectQ.
Created exams are listed at /student/regularexam.
"""
import json
import logging
import random

from django.conf import settings
from django.db import connections
from django.utils import timezone

from .ai_question_generator import generate_questions_from_ai
from .subject_question_tables import next_qid_for_chapter_topic, subject_question_table_name

logger = logging.getLogger(__name__)


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
            return "type LIKE '%বহুনির্বাচনি%'"
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
    questions (even after asking Home AI first, then Cloud AI), this returns None so
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
    try:
        with conn.cursor() as cur:
            for level_tr, class_level, subject_tr, sq in scope:
                table_name = subject_question_table_name(level_tr, class_level, subject_tr)
                if not _table_exists(cur, table_name):
                    continue
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
                    "DELETE FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s",
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
    try:
        with conn.cursor() as cur:
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
                    "SELECT set_key FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_type = 'topic'",
                    [alias, level_tr, class_level, subject_tr]
                )
                existing_topic_keys = {r[0] for r in cur.fetchall()}
                tbl = table_name.replace('`', '``')
                mcq = _mcq_condition(cur, tbl)
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
                    "SELECT COUNT(*) FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_type = 'chapter'",
                    [alias, level_tr, class_level, subject_tr]
                )
                if cur.fetchone()[0] == 0:
                    added += _create_chapter_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, chapter_list, progress=progress, ai_stats=ai_stats)
                # Subject: same
                cur.execute(
                    "SELECT COUNT(*) FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_type = 'subject'",
                    [alias, level_tr, class_level, subject_tr]
                )
                if cur.fetchone()[0] == 0:
                    added += _create_subject_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, progress=progress, ai_stats=ai_stats)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    msg = 'Add Exam: added %d missing set(s).' % added
    if skipped:
        msg += ' Skipped (could not build %d unique-question topic set(s) via Home/Cloud AI): %s' % (
            len(skipped), ', '.join(skipped))
    return {'message': msg}
