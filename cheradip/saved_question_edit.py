"""Read-only recovery of legacy saved sets containing qid-only placeholder rows."""
from copy import deepcopy
import re

from django.db import connections

from .subject_question_tables import subject_question_table_name


def _normalized(value):
    return re.sub(r"[\W_]+", " ", str(value or "").casefold()).strip()


def _placeholder(row):
    if not isinstance(row, dict) or row.get('qid') is None:
        return False
    text = str(row.get('question') or '').strip()
    return not text or text.startswith('— (')


def recover_saved_question_edit(obj, db_alias):
    """Return a recovered copy only; never replace the saved record or paid history.

    A qid is only unique inside a subject table. Match the catalog uniquely first;
    never search unrelated subjects and silently choose a matching qid.
    """
    questions = deepcopy(obj.questions if isinstance(obj.questions, list) else [])
    layout = deepcopy(obj.layout_settings if isinstance(obj.layout_settings, dict) else {})
    missing = [row for row in questions if _placeholder(row)]
    context = layout.get('creatorContext') or layout.get('context') or {}
    context = dict(context) if isinstance(context, dict) else {}
    complete = all(context.get(key) for key in ('level_tr', 'class_level', 'subject_tr'))
    provenance = {row.get('table') for row in questions if isinstance(row, dict) and row.get('table')
                  and row.get('db_alias', db_alias) == db_alias}
    if not missing and complete:
        return questions, layout
    with connections[db_alias].cursor() as cursor:
        cursor.execute("SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject'")
        catalog_columns = {str(row[0]).lower() for row in cursor.fetchall()}
        has_sq = 'sq' in catalog_columns
        cursor.execute('SELECT level_tr, class_level, subject_tr, subject_name, subject_code' + (', sq' if has_sq else '') + ' FROM cheradip_subject')
        name = _normalized(obj.name)
        label = _normalized(layout.get('subjectName'))
        candidates = {}
        for row in cursor.fetchall():
            level, class_level, subject, subject_name, code = row[:5]
            if any(context.get(key) and _normalized(context[key]) != _normalized(value)
                   for key, value in [('level_tr', level), ('class_level', class_level), ('subject_tr', subject)]):
                continue
            subject_key = _normalized(subject)
            matches_name = bool(subject_key) and (name == subject_key or name.startswith(subject_key + ' '))
            matches_label = bool(label) and label in {_normalized(subject), _normalized(subject_name)}
            matches_table = len(provenance) == 1 and subject_question_table_name(level, class_level, subject) in provenance
            if provenance and not matches_table:
                continue
            if not complete and not (matches_table or matches_name or matches_label):
                continue
            key = (str(level), str(class_level), str(subject))
            candidates[key] = {**context, 'level_tr': level, 'class_level': class_level,
                               'subject_tr': subject, 'subject_name': subject_name or subject,
                               'name': subject_name or subject, 'subject_code': code or '',
                               **({'sq': row[5]} if has_sq and row[5] in (25, 30) else {})}
        if len(candidates) != 1:
            if missing:
                raise ValueError('The saved question subject could not be matched uniquely. Select the correct subject from the Question Library before creating a replacement set.')
            return questions, layout
        context = next(iter(candidates.values()))
        layout['creatorContext'] = context
        if not missing:
            return questions, layout
        table = subject_question_table_name(context['level_tr'], context['class_level'], context['subject_tr'])
        cursor.execute('SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s', [table])
        available = {str(row[0]).lower() for row in cursor.fetchall()}
        pk = 'qid' if 'qid' in available else 'id'
        fields = [key for key in ('subject', 'chapter_no', 'chapter', 'topic_no', 'topic', 'question',
                  'option_1', 'option_2', 'option_3', 'option_4', 'answer', 'explanation', 'explanation2',
                  'explanation3', 'type', 'level', 'subsource') if key in available]
        if pk not in available or 'question' not in fields:
            raise ValueError('The source question table is unavailable. Ask the administrator to synchronize the subject data.')
        ids = list(dict.fromkeys(str(row['qid']) for row in missing))
        recovered = {}
        for offset in range(0, len(ids), 500):
            batch = ids[offset:offset + 500]
            cursor.execute('SELECT `' + pk + '`, ' + ', '.join('`' + key + '`' for key in fields)
                           + ' FROM `' + table + '` WHERE `' + pk + '` IN (' + ','.join(['%s'] * len(batch)) + ')', batch)
            for record in cursor.fetchall():
                data = dict(zip(fields, record[1:]))
                if str(data.get('question') or '').strip():
                    recovered[str(record[0])] = data
        unresolved = [str(row['qid']) for row in missing if str(row['qid']) not in recovered]
        if unresolved:
            raise ValueError(f'{len(unresolved)} saved question(s) are no longer available in the matching subject table. Ask the administrator to synchronize the missing questions.')
        for row in questions:
            if _placeholder(row):
                # Keep the original qid/order and any saved per-question layout metadata.
                row.update(recovered[str(row['qid'])])
    return questions, layout
