"""
Exam creation actions called from admin Settings: Create Exam and Add Exam.
Uses filters (level_tr, class_level, subject_tr, chapter, topic) and db_alias.
Stores exam sets in cheradip_exam_set; optionally summary in cheradip_subject.ChapterQ/SubjectQ.
Created exams are listed at /student/regularexam.
"""
import json
import random
from django.db import connections
from django.utils import timezone

from .subject_question_tables import subject_question_table_name


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


def _create_topic_sets(cursor, table_name, level_tr, class_level, subject_tr, sq, db_alias, chapter_list, topic_list):
    """Create topic-based exam sets: chapter_no.topic_no: Topic Name (e.g. 1.1: All Topics), ordered by chapter_no then topic_no."""
    tbl = table_name.replace('`', '``')
    # Build list of (chapter_no, topic_no, topic_name) ordered by chapter_no, topic_no (numeric)
    order_sql = "ORDER BY CAST(COALESCE(NULLIF(TRIM(chapter_no), ''), '0') AS UNSIGNED), CAST(COALESCE(NULLIF(TRIM(topic_no), ''), '0') AS UNSIGNED), topic"
    if chapter_list:
        placeholders = ', '.join(['%s'] * len(chapter_list))
        cursor.execute(
            "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE (chapter_no IN (" + placeholders + ") OR chapter IN (" + placeholders + ")) "
            "AND topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + order_sql,
            list(chapter_list) + list(chapter_list)
        )
        topics = cursor.fetchall() or []
    else:
        cursor.execute(
            "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + order_sql
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
    for ch_no, topic_no, topic_name in topics:
        tname = (topic_name or '').strip() or ('Topic %s' % (topic_no or ''))
        ch_no_s = (ch_no or '').strip() or '0'
        topic_no_s = (topic_no or '').strip() or '0'
        cursor.execute(
            "SELECT qid FROM `" + tbl + "` WHERE (chapter_no = %s OR chapter = %s) AND topic = %s ORDER BY RAND()",
            [ch_no, ch_no, topic_name]
        )
        all_qids = [r[0] for r in cursor.fetchall()]
        if not all_qids:
            continue
        if len(all_qids) >= sq:
            qids = all_qids[:sq]
            random.shuffle(qids)
        else:
            qids = list(all_qids)
            random.shuffle(qids)
            while len(qids) < sq:
                qids.append(random.choice(all_qids))
            random.shuffle(qids)
        set_key = "%s.%s" % (ch_no_s, topic_no_s)
        name_label = "%s.%s: %s" % (ch_no_s, topic_no_s, tname)
        cursor.execute(
            "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'topic', %s, %s, %s, %s)",
            [db_alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(qids), now]
        )
        created += 1
    return created


def _create_chapter_sets(cursor, table_name, level_tr, class_level, subject_tr, db_alias, chapter_list):
    """Chapter-based: 0: Chapter name, 1: Chapter name, ... 10: Chapter name (11 sets of 10 q each), then 11-20: Ch2, etc."""
    tbl = table_name.replace('`', '``')
    if chapter_list:
        placeholders = ', '.join(['%s'] * len(chapter_list))
        cursor.execute(
            "SELECT DISTINCT chapter_no, chapter FROM `" + tbl + "` WHERE chapter_no IN (" + placeholders + ") OR chapter IN (" + placeholders + ") ORDER BY chapter_no, chapter",
            list(chapter_list) + list(chapter_list)
        )
    else:
        cursor.execute(
            "SELECT DISTINCT chapter_no, chapter FROM `" + tbl + "` WHERE (chapter_no IS NOT NULL AND TRIM(COALESCE(chapter_no, '')) != '') OR (chapter IS NOT NULL AND TRIM(COALESCE(chapter, '')) != '') ORDER BY chapter_no, chapter"
        )
    chapters = cursor.fetchall() or []
    now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    set_index = 0
    for ch_no, ch_name in chapters:
        cname = (ch_name or '').strip() or ('Chapter %s' % (ch_no or ''))
        cursor.execute(
            "SELECT qid FROM `" + tbl + "` WHERE (chapter_no = %s OR chapter = %s) ORDER BY RAND()",
            [ch_no, ch_name]
        )
        all_qids = [r[0] for r in cursor.fetchall()]
        if not all_qids:
            continue
        random.shuffle(all_qids)
        # 10 sets per chapter (0-9), 10 questions each (max 60 for 6 chapters)
        for s in range(10):
            start = s * 10
            chunk = all_qids[start:start + 10]
            if not chunk:
                break
            set_key = str(set_index)
            name_label = "%s: %s" % (set_key, cname)
            cursor.execute(
                "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'chapter', %s, %s, %s, %s)",
                [db_alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(chunk), now]
            )
            set_index += 1
    return set_index


def _create_subject_sets(cursor, table_name, level_tr, class_level, subject_tr, db_alias):
    """Subject-based: 0.01 Subject name, 0.02, ... 0.99; order questions (999 order), 30 per set, max 99 sets."""
    tbl = table_name.replace('`', '``')
    cursor.execute(
        "SELECT qid FROM `" + tbl + "` ORDER BY COALESCE(NULLIF(TRIM(chapter_no), ''), '0'), COALESCE(NULLIF(TRIM(topic_no), ''), '0'), qid LIMIT 999"
    )
    ordered_qids = [r[0] for r in cursor.fetchall()]
    if not ordered_qids:
        return 0
    now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    per_set = 30
    count = 0
    for i in range(1, 100):
        start = (i - 1) * per_set
        chunk = ordered_qids[start:start + per_set]
        if not chunk:
            break
        set_key = "0.%02d" % i
        name_label = "%s %s" % (set_key, subject_tr or 'Subject')
        cursor.execute(
            "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'subject', %s, %s, %s, %s)",
            [db_alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(chunk), now]
        )
        count += 1
    return count


def run_create_exam(db_alias, filters):
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
    try:
        with conn.cursor() as cur:
            for level_tr, class_level, subject_tr, sq in scope:
                table_name = subject_question_table_name(level_tr, class_level, subject_tr)
                if not _table_exists(cur, table_name):
                    continue
                # Delete existing exam sets for this subject (recreate)
                cur.execute(
                    "DELETE FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s",
                    [alias, level_tr, class_level, subject_tr]
                )
                created_topic += _create_topic_sets(cur, table_name, level_tr, class_level, subject_tr, sq, alias, chapter_list, topic_list)
                created_chapter += _create_chapter_sets(cur, table_name, level_tr, class_level, subject_tr, alias, chapter_list)
                created_subject += _create_subject_sets(cur, table_name, level_tr, class_level, subject_tr, alias)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    msg = 'Created exam sets: %d topic, %d chapter, %d subject.' % (created_topic, created_chapter, created_subject)
    return {'message': msg}


def run_add_exam(db_alias, filters):
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
    try:
        with conn.cursor() as cur:
            for level_tr, class_level, subject_tr, sq in scope:
                table_name = subject_question_table_name(level_tr, class_level, subject_tr)
                if not _table_exists(cur, table_name):
                    continue
                # Topic: only add sets for topics that don't have an exam_set row
                cur.execute(
                    "SELECT set_key FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_type = 'topic'",
                    [alias, level_tr, class_level, subject_tr]
                )
                existing_topic_keys = {r[0] for r in cur.fetchall()}
                tbl = table_name.replace('`', '``')
                order_sql = "ORDER BY CAST(COALESCE(NULLIF(TRIM(chapter_no), ''), '0') AS UNSIGNED), CAST(COALESCE(NULLIF(TRIM(topic_no), ''), '0') AS UNSIGNED), topic"
                if chapter_list:
                    ph = ', '.join(['%s'] * len(chapter_list))
                    cur.execute(
                        "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE (chapter_no IN (" + ph + ") OR chapter IN (" + ph + ")) "
                        "AND topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + order_sql,
                        list(chapter_list) + list(chapter_list)
                    )
                else:
                    cur.execute(
                        "SELECT DISTINCT chapter_no, topic_no, topic FROM `" + tbl + "` WHERE topic IS NOT NULL AND TRIM(COALESCE(topic, '')) != '' " + order_sql
                    )
                topics = cur.fetchall() or []
                if topic_list:
                    topic_set = {s.strip() for s in topic_list if s and str(s).strip()}
                    topics = [
                        t for t in topics
                        if (t[2] or '').strip() in topic_set or (t[1] is not None and str(t[1]).strip() in topic_set)
                    ]
                now = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                for ch_no, topic_no, topic_name in topics:
                    set_key = "%s.%s" % ((ch_no or '').strip() or '0', (topic_no or '').strip() or '0')
                    if set_key in existing_topic_keys:
                        continue
                    tname = (topic_name or '').strip() or ('Topic %s' % (topic_no or ''))
                    cur.execute(
                        "SELECT qid FROM `" + tbl + "` WHERE (chapter_no = %s OR chapter = %s) AND topic = %s ORDER BY RAND()",
                        [ch_no, ch_no, topic_name]
                    )
                    all_qids = [r[0] for r in cur.fetchall()]
                    if not all_qids:
                        continue
                    if len(all_qids) >= sq:
                        qids = all_qids[:sq]
                        random.shuffle(qids)
                    else:
                        qids = list(all_qids)
                        random.shuffle(qids)
                        while len(qids) < sq:
                            qids.append(random.choice(all_qids))
                        random.shuffle(qids)
                    name_label = "%s.%s: %s" % ((ch_no or '').strip() or '0', (topic_no or '').strip() or '0', tname)
                    cur.execute(
                        "INSERT INTO cheradip_exam_set (db_alias, level_tr, class_level, subject_tr, exam_type, set_key, name_label, qids_json, created_at) VALUES (%s, %s, %s, %s, 'topic', %s, %s, %s, %s)",
                        [alias, level_tr, class_level, subject_tr, set_key, name_label, json.dumps(qids), now]
                    )
                    added += 1
                # Chapter: check existing chapter set count; add if missing
                cur.execute(
                    "SELECT COUNT(*) FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_type = 'chapter'",
                    [alias, level_tr, class_level, subject_tr]
                )
                if cur.fetchone()[0] == 0:
                    added += _create_chapter_sets(cur, table_name, level_tr, class_level, subject_tr, alias, chapter_list)
                # Subject: same
                cur.execute(
                    "SELECT COUNT(*) FROM cheradip_exam_set WHERE db_alias = %s AND level_tr = %s AND class_level = %s AND subject_tr = %s AND exam_type = 'subject'",
                    [alias, level_tr, class_level, subject_tr]
                )
                if cur.fetchone()[0] == 0:
                    added += _create_subject_sets(cur, table_name, level_tr, class_level, subject_tr, alias)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    return {'message': 'Add Exam: added %d missing set(s).' % added}
