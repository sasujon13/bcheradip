"""
Custom Django Admin views: list databases, list tables per database,
and browse/add/delete/edit rows + bulk import CSV/JSON for any table.
"""
import base64
import csv
import html
import io
import json
import re

from django.contrib import admin
from django.utils.dateparse import parse_datetime
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.template.response import TemplateResponse
from django.db import connections
from django.urls import reverse

from backend.admin_app_list import get_app_list_by_database, build_db_tabs_for_index
from django.core.paginator import Paginator
from django.http import HttpResponseNotFound, HttpResponseBadRequest, JsonResponse
from django.contrib import messages
from django.utils import timezone

# Aliases and display names for the 4 databases
DATABASE_MENU = [
    ('default', 'cheradip (default)'),
    ('hsc', 'HSC'),
    ('honours', 'Honours'),
    ('job', 'Job'),
]

# Allowed table names (cheradip_* only)
def _allowed_table_name(name):
    if not name or not isinstance(name, str):
        return False
    return bool(re.match(r'^cheradip_[a-z0-9_]+$', name.strip().lower()))


def _get_table_columns(conn, table_name):
    """Return list of column names for the table (from introspection)."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM `%s` LIMIT 0" % table_name.replace('`', '``'))
        return [row[0] for row in cursor.description] if cursor.description else []


def _get_pk_column(columns):
    """Return column name to use for ordering and row identity (id if present, else first column)."""
    if not columns:
        return 'id'
    return 'id' if 'id' in columns else columns[0]


def _get_column_types(conn, table_name, db_name):
    """Return dict mapping column name -> 'datetime' | 'date' | None for MySQL."""
    result = {}
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
            [db_name, table_name]
        )
        for row in cursor.fetchall() or []:
            col, dtype = (row[0], (row[1] or '').lower())
            if dtype in ('datetime', 'timestamp'):
                result[col] = 'datetime'
            elif dtype == 'date':
                result[col] = 'date'
            else:
                result[col] = None
    return result


def _parse_datetime_for_mysql(value):
    """
    Parse a form value (locale or ISO string, or already MySQL format) to MySQL datetime string.
    Returns None if value is empty or unparseable.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Already MySQL-style
    if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?(\.\d+)?$', s):
        return s[:19] if len(s) > 19 else s
    # ISO with T
    parsed = parse_datetime(s)
    if parsed:
        return parsed.strftime('%Y-%m-%d %H:%M:%S')
    try:
        from dateutil.parser import parse as dateutil_parse
        parsed = dateutil_parse(s)
        return parsed.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    return None


def _format_cell_for_edit(value, data_type):
    """Format a cell value for display in the edit form (MySQL-compatible for datetime/date)."""
    if value is None:
        return ''
    if data_type == 'datetime':
        if hasattr(value, 'strftime'):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        s = str(value).strip()
        if s:
            parsed = parse_datetime(s)
            if parsed:
                return parsed.strftime('%Y-%m-%d %H:%M:%S')
            try:
                from dateutil.parser import parse as dateutil_parse
                parsed = dateutil_parse(s)
                return parsed.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
        return s
    if data_type == 'date':
        if hasattr(value, 'strftime'):
            return value.strftime('%Y-%m-%d')
        s = str(value).strip()
        if s and len(s) >= 10:
            return s[:10]
        return s
    return str(value)


def _get_row_count(conn, table_name, where_clause=None, where_params=None):
    safe_table = table_name.replace('`', '``')
    sql = "SELECT COUNT(*) FROM `%s`" % safe_table
    params = []
    if where_clause:
        sql += " WHERE " + where_clause
        params = list(where_params or [])
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()[0]


def _get_table_rows(conn, table_name, limit, offset, order_by_column, where_clause=None, where_params=None):
    """order_by_column: column name for ORDER BY (e.g. id or first column)."""
    order_col = order_by_column.replace('`', '``')
    safe_table = table_name.replace('`', '``')
    sql = "SELECT * FROM `%s`" % safe_table
    params = []
    if where_clause:
        sql += " WHERE " + where_clause
        params = list(where_params or [])
    sql += " ORDER BY `%s` LIMIT %%s OFFSET %%s" % order_col
    params.extend([limit, offset])
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [row[0] for row in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return columns, rows


def _get_pending_question_request_filter_options(conn, table_name):
    """Return distinct subject_tr, type, status for cheradip_pending_question_request (for filter dropdowns)."""
    if table_name != 'cheradip_pending_question_request':
        return None
    safe_table = table_name.replace('`', '``')
    result = {'subject_tr_list': [], 'type_list': [], 'status_list': []}
    with conn.cursor() as cursor:
        for col, key in [('subject_tr', 'subject_tr_list'), ('type', 'type_list'), ('status', 'status_list')]:
            try:
                cursor.execute(
                    "SELECT DISTINCT `%s` FROM `%s` WHERE `%s` IS NOT NULL AND TRIM(COALESCE(`%s`,'')) != '' ORDER BY 1" % (
                        col.replace('`', '``'), safe_table, col.replace('`', '``'), col.replace('`', '``')
                    )
                )
                result[key] = [str(r[0]).strip() for r in cursor.fetchall() if r[0] is not None and str(r[0]).strip()]
            except Exception:
                pass
    return result


def _insert_row(conn, table_name, columns, data):
    """Insert one row. data: dict column -> value. Skip id if empty (auto_increment)."""
    cols = [c for c in columns if c in data and data[c] is not None and str(data[c]).strip() != '']
    if not cols:
        return False
    if 'id' in data and (data['id'] is None or str(data['id']).strip() == ''):
        cols = [c for c in cols if c != 'id']
    placeholders = ', '.join(['%s'] * len(cols))
    col_list = ', '.join('`%s`' % c.replace('`', '``') for c in cols)
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO `%s` (%s) VALUES (%s)" % (table_name.replace('`', '``'), col_list, placeholders),
            [data[c] for c in cols]
        )
    return True


def _delete_rows(conn, table_name, pk_column, ids):
    """Delete rows where pk_column IN (ids). ids are used as-is (int or string)."""
    if not ids:
        return 0
    placeholders = ', '.join(['%s'] * len(ids))
    pk_esc = pk_column.replace('`', '``')
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM `%s` WHERE `%s` IN (%s)" % (table_name.replace('`', '``'), pk_esc, placeholders),
            ids
        )
        return cursor.rowcount


def _deny_pending_question_rows(conn, pk_column, ids):
    """
    Reject edit requests: DELETE rows from cheradip_pending_question_request only.
    Does not modify subject question tables (live questions unchanged).
    """
    return _delete_rows(conn, 'cheradip_pending_question_request', pk_column, ids)


def _update_row(conn, table_name, columns, pk_column, pk_value, data):
    """Update one row by primary key column."""
    cols = [c for c in columns if c != pk_column and c in data]
    if not cols:
        return False
    set_clause = ', '.join('`%s` = %%s' % c.replace('`', '``') for c in cols)
    pk_esc = pk_column.replace('`', '``')
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE `%s` SET %s WHERE `%s` = %%s" % (table_name.replace('`', '``'), set_clause, pk_esc),
            [data[c] for c in cols] + [pk_value]
        )
    return True


PENDING_MODAL_STRIP_FIELDS = frozenset({
    'question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer',
    'explanation', 'explanation2', 'explanation3',
})
PENDING_MODAL_TEXTAREA_FIELDS = frozenset({
    'question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer',
    'explanation', 'explanation2', 'explanation3',
})


def _pending_row_values_for_modal(row_data, columns, column_types):
    """Build string values for the edit modal (plain text for markup-heavy fields)."""
    out = {}
    for c in columns:
        v = row_data.get(c)
        if c in PENDING_MODAL_STRIP_FIELDS:
            s = _strip_red_markup(v)
            out[c] = '' if s is None else str(s)
            continue
        dt = column_types.get(c)
        if v is None:
            out[c] = ''
        elif dt in ('datetime', 'date'):
            out[c] = _format_cell_for_edit(v, dt)
        else:
            out[c] = str(v) if v is not None else ''
    return out


@staff_member_required
def pending_question_row_json(request, db_alias, table_name, pk):
    """GET JSON for one cheradip_pending_question_request row (HSC) — for Edit & Approve modal."""
    if request.method != 'GET':
        return HttpResponseBadRequest('GET only')
    table_name = table_name.strip().lower()
    if db_alias != 'hsc' or table_name != 'cheradip_pending_question_request':
        return HttpResponseNotFound('Not available for this table.')
    if not _allowed_table_name(table_name):
        return HttpResponseBadRequest('Invalid table name.')
    if db_alias not in connections:
        return HttpResponseNotFound('Unknown database alias.')
    conn = connections[db_alias]
    db_name = conn.settings_dict.get('NAME', db_alias)
    columns = _get_table_columns(conn, table_name)
    if not columns:
        return HttpResponseNotFound('Table not found.')
    pk_column = _get_pk_column(columns)
    column_types = _get_column_types(conn, table_name, db_name)
    with conn.cursor() as cursor:
        pk_esc = pk_column.replace('`', '``')
        cursor.execute(
            "SELECT * FROM `%s` WHERE `%s` = %%s" % (table_name.replace('`', '``'), pk_esc),
            [pk]
        )
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'ok': False, 'error': 'Row not found.'}, status=404)
    row_data = dict(zip(columns, row))
    values = _pending_row_values_for_modal(row_data, columns, column_types)
    return JsonResponse(
        {'ok': True, 'pk': str(pk), 'pk_column': pk_column, 'columns': columns, 'values': values},
        json_dumps_params={'ensure_ascii': False},
    )


def _strip_red_markup(value):
    """
    Pending question fields may store:
    - <!--CERADIP_PLAIN:base64--> + diff HTML (added=blue <b>, deleted=<b><del> darkred) — use decoded plain.
    - Legacy: whole field in <span style="color:red">…</span> — strip tags to plain text.
    """
    if value is None:
        return None
    s = str(value)
    if not s.strip():
        return s or None
    m = re.match(r'^<!--CERADIP_PLAIN:([A-Za-z0-9+/=]+)-->', s)
    if m:
        try:
            b64 = m.group(1)
            pad = '=' * (-len(b64) % 4)
            raw = base64.b64decode(b64 + pad)
            return raw.decode('utf-8')
        except Exception:
            pass
    s2 = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s2)


def _approve_pending_question_rows(conn, db_name, pk_column, ids):
    """
    Approve selected rows in cheradip_pending_question_request (HSC): insert/update into
    the subject question table (with red markup stripped), then delete the pending row.
    Returns (success_count, list of error strings).
    """
    from cheradip.subject_question_tables import subject_question_table_name, next_qid_for_chapter_topic
    table_name = 'cheradip_pending_question_request'
    success = 0
    errors = []
    with conn.cursor() as cursor:
        for pk in ids:
            try:
                cursor.execute(
                    "SELECT * FROM `%s` WHERE `%s` = %%s" % (table_name.replace('`', '``'), pk_column.replace('`', '``')),
                    [pk]
                )
                row = cursor.fetchone()
                if not row:
                    errors.append('Row %s not found.' % pk)
                    continue
                columns = [col[0] for col in cursor.description]
                row_data = dict(zip(columns, row))
                level_tr = (row_data.get('level_tr') or '').strip() or ''
                class_level = (row_data.get('class_level') or '').strip() or ''
                subject_tr = (row_data.get('subject_tr') or '').strip() or ''
                if not subject_tr:
                    errors.append('Row %s has no subject_tr.' % pk)
                    continue
                stored_table = (row_data.get('table') or '').strip()
                target_table = stored_table if stored_table else subject_question_table_name(level_tr, class_level, subject_tr)
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                    [db_name, target_table]
                )
                if not cursor.fetchone():
                    errors.append('Subject table not found for row %s: %s' % (pk, target_table))
                    continue
                requested_qid = (row_data.get('requested_qid') or '').strip()
                now_sql = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                level_val = (row_data.get('level_tr') or row_data.get('level') or '').strip() or None
                subsource_val = (row_data.get('subsource') or '').strip() or None
                updated_by_val = (row_data.get('updated_by') or '').strip() or 'Cheradip'
                question_val = _strip_red_markup(row_data.get('question'))
                option_1_val = _strip_red_markup(row_data.get('option_1'))
                option_2_val = _strip_red_markup(row_data.get('option_2'))
                option_3_val = _strip_red_markup(row_data.get('option_3'))
                option_4_val = _strip_red_markup(row_data.get('option_4'))
                explanation_val = _strip_red_markup(row_data.get('explanation'))
                explanation2_val = _strip_red_markup(row_data.get('explanation2'))
                explanation3_val = _strip_red_markup(row_data.get('explanation3'))
                if requested_qid:
                    cursor.execute(
                        """UPDATE `%s` SET subject=%%s, chapter_no=%%s, chapter=%%s, topic_no=%%s, topic=%%s, question=%%s,
                           option_1=%%s, option_2=%%s, option_3=%%s, option_4=%%s, answer=%%s, explanation=%%s,
                           explanation2=%%s, explanation3=%%s, type=%%s, level=%%s, subsource=%%s, updated_at=%%s, updated_by=%%s
                           WHERE qid=%%s""" % target_table.replace('`', '``'),
                        [
                            row_data.get('subject_tr'), row_data.get('chapter_no'), row_data.get('chapter'),
                            row_data.get('topic_no'), row_data.get('topic'), question_val,
                            option_1_val, option_2_val, option_3_val, option_4_val,
                            row_data.get('answer'), explanation_val, explanation2_val, explanation3_val,
                            row_data.get('type'), level_val, subsource_val, now_sql, updated_by_val, requested_qid
                        ]
                    )
                    qid = requested_qid
                else:
                    qid = next_qid_for_chapter_topic(
                        target_table,
                        row_data.get('chapter_no') or '0',
                        row_data.get('topic_no') or '0',
                        using='hsc'
                    )
                    cursor.execute(
                        """INSERT INTO `%s` (qid, subject, chapter_no, chapter, topic_no, topic, question, option_1, option_2, option_3, option_4, answer, explanation, explanation2, explanation3, type, level, subsource, created_at, updated_at, updated_by)
                           VALUES (%%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s)""" % target_table.replace('`', '``'),
                        [
                            qid, row_data.get('subject_tr'), row_data.get('chapter_no'), row_data.get('chapter'),
                            row_data.get('topic_no'), row_data.get('topic'), question_val,
                            option_1_val, option_2_val, option_3_val, option_4_val,
                            row_data.get('answer'), explanation_val, explanation2_val, explanation3_val,
                            row_data.get('type'), level_val, subsource_val, now_sql, now_sql, updated_by_val
                        ]
                    )
                cursor.execute(
                    "DELETE FROM `%s` WHERE `%s`=%%s" % (table_name.replace('`', '``'), pk_column.replace('`', '``')),
                    [pk]
                )
                success += 1
            except Exception as e:
                errors.append('Row %s: %s' % (pk, str(e)))
    return success, errors


@staff_member_required
def databases_list(request):
    """Redirect /admin/databases/ to /admin/databases/default/ by default."""
    return redirect('admin:database_tables', db_alias='default')
    models = []
    for alias, label in DATABASE_MENU:
        if alias not in connections:
            continue
        url = f'/admin/databases/{alias}/'
        models.append({
            'model': None,
            'name': label,
            'object_name': label,
            'perms': {'add': True, 'change': True, 'view': True, 'delete': False},
            'admin_url': url,
            'add_url': url,
            'view_only': False,
        })
    models.sort(key=lambda x: x['name'].lower())
    app_list = [{
        'name': 'Databases',
        'app_label': 'cheradip',
        'app_url': reverse('admin:index', current_app=admin.site.name),
        'has_module_perms': True,
        'models': models,
    }]
    context = {
        **admin.site.each_context(request),
        'title': admin.site.index_title,
        'subtitle': None,
        'app_list': app_list,
        'db_tabs': db_tabs,
        'current_db': None,
        'table_links_only': True,
    }
    request.current_app = admin.site.name
    return TemplateResponse(request, admin.site.index_template or 'admin/index.html', context)


@staff_member_required
def database_tables(request, db_alias):
    """Same UI as admin index with ?db=hsc: tabs + full table list for this DB."""
    if db_alias not in connections:
        from django.http import HttpResponseNotFound
        return HttpResponseNotFound('Unknown database alias: %s' % db_alias)
    db_tabs = build_db_tabs_for_index(active_alias=db_alias, use_databases_path=True)
    app_list = get_app_list_by_database(request, force_db=db_alias)
    context = {
        **admin.site.each_context(request),
        'title': admin.site.index_title,
        'subtitle': None,
        'app_list': app_list,
        'db_tabs': db_tabs,
        'current_db': db_alias,
        'table_links_only': True,
    }
    request.current_app = admin.site.name
    return TemplateResponse(request, admin.site.index_template or 'admin/index.html', context)


PAGE_SIZE = 50


def _settings_filter_options(conn, db_alias):
    """Get level, class, subject (and optionally chapter, topic) options for Settings form. Uses cheradip_subject; for chapters/topics requires subject table."""
    levels, class_levels, subjects, chapters, topics = [], [], [], [], []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'cheradip_subject'"
            )
            if not cur.fetchone():
                return levels, class_levels, subjects, chapters, topics
            cur.execute(
                "SELECT DISTINCT level_tr FROM cheradip_subject WHERE level_tr IS NOT NULL AND TRIM(COALESCE(level_tr, '')) != '' ORDER BY level_tr"
            )
            levels = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
            cur.execute(
                "SELECT DISTINCT class_level FROM cheradip_subject WHERE class_level IS NOT NULL AND TRIM(COALESCE(class_level, '')) != '' ORDER BY class_level"
            )
            class_levels = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
            cur.execute(
                "SELECT DISTINCT subject_tr FROM cheradip_subject WHERE subject_tr IS NOT NULL AND TRIM(COALESCE(subject_tr, '')) != '' ORDER BY subject_tr"
            )
            subjects = [str(r[0]).strip() for r in cur.fetchall() if r[0]]
    except Exception:
        pass
    return levels, class_levels, subjects, chapters, topics


@staff_member_required
def database_settings(request, db_alias):
    """Settings page: Create Exam / Add Exam with optional filters. Same tab row as database_tables."""
    if db_alias not in connections:
        return HttpResponseNotFound('Unknown database alias: %s' % db_alias)
    conn = connections[db_alias]
    db_tabs = build_db_tabs_for_index(active_alias=db_alias, use_databases_path=True, settings_active=True)
    levels, class_levels, subjects, chapters, topics = _settings_filter_options(conn, db_alias)
    filters = {
        'level_tr': request.GET.get('level_tr') or request.POST.get('level_tr') or '',
        'class_level': request.GET.get('class_level') or request.POST.get('class_level') or '',
        'group': request.GET.get('group') or request.POST.get('group') or '',
        'subject_tr': request.GET.get('subject_tr') or request.POST.get('subject_tr') or '',
        'chapter': request.GET.get('chapter') or request.POST.get('chapter') or '',
        'topic': request.GET.get('topic') or request.POST.get('topic') or '',
    }
    if request.method == 'POST':
        action = request.POST.get('action')
        if action in ('create_exam', 'add_exam'):
            try:
                from cheradip.exam_actions import run_create_exam, run_add_exam
                if action == 'create_exam':
                    result = run_create_exam(db_alias, filters)
                else:
                    result = run_add_exam(db_alias, filters)
                messages.success(request, result.get('message', 'Done.'))
            except Exception as e:
                messages.error(request, 'Action failed: %s' % str(e))
            return redirect('admin:database_settings', db_alias=db_alias)
    context = {
        **admin.site.each_context(request),
        'title': admin.site.index_title,
        'subtitle': None,
        'db_tabs': db_tabs,
        'current_db': db_alias,
        'levels': levels,
        'class_levels': class_levels,
        'subjects': subjects,
        'chapters': chapters,
        'topics': topics,
        'filters': filters,
    }
    request.current_app = admin.site.name
    return TemplateResponse(request, 'admin/database_settings.html', context)


@staff_member_required
def database_table_data(request, db_alias, table_name):
    """Browse rows, add row, delete selected, bulk import CSV/JSON."""
    if db_alias not in connections:
        return HttpResponseNotFound('Unknown database alias: %s' % db_alias)
    table_name = table_name.strip().lower()
    if not _allowed_table_name(table_name):
        return HttpResponseBadRequest('Invalid table name.')
    conn = connections[db_alias]
    db_name = conn.settings_dict.get('NAME', db_alias)
    label = dict(DATABASE_MENU).get(db_alias, db_alias)
    columns = _get_table_columns(conn, table_name)
    if not columns:
        messages.error(request, 'Table not found or has no columns.')
        return redirect('admin:database_tables', db_alias=db_alias)

    # POST: add / delete / import
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            data = {c: request.POST.get('field_%s' % c) for c in columns}
            try:
                _insert_row(conn, table_name, columns, data)
                messages.success(request, 'Row added.')
            except Exception as e:
                messages.error(request, 'Add failed: %s' % str(e))
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)

        if action in ('deny', 'delete') and db_alias == 'hsc' and table_name == 'cheradip_pending_question_request':
            ids = request.POST.getlist('ids')
            pk_col = _get_pk_column(columns)
            try:
                ids = [i.strip() for i in ids if i and str(i).strip()]
                if not ids:
                    messages.error(request, 'Select at least one row to reject.')
                else:
                    n = _deny_pending_question_rows(conn, pk_col, ids)
                    messages.success(
                        request,
                        'Removed %s pending edit request(s). Live questions in subject tables were not changed.' % n,
                    )
            except Exception as e:
                messages.error(request, 'Reject failed: %s' % str(e))
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)

        if action == 'delete':
            ids = request.POST.getlist('ids')
            pk_col = _get_pk_column(columns)
            try:
                ids = [i.strip() for i in ids if i and str(i).strip()]
                n = _delete_rows(conn, table_name, pk_col, ids)
                messages.success(request, 'Deleted %s row(s).' % n)
            except Exception as e:
                messages.error(request, 'Delete failed: %s' % str(e))
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)

        if action == 'import':
            f = request.FILES.get('import_file')
            fmt = request.POST.get('import_format', 'csv').lower()
            csv_has_header = request.POST.get('csv_has_header') == 'on'
            if not f:
                messages.error(request, 'No file uploaded.')
            else:
                try:
                    content = f.read().decode('utf-8-sig', errors='replace')
                    count = _bulk_import(conn, table_name, columns, content, fmt, csv_has_header)
                    messages.success(request, 'Imported %s row(s).' % count)
                except Exception as e:
                    messages.error(request, 'Import failed: %s' % str(e))
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)

        if action == 'approve' and db_alias == 'hsc' and table_name == 'cheradip_pending_question_request':
            ids = request.POST.getlist('ids')
            ids = [i.strip() for i in ids if i and str(i).strip()]
            if not ids:
                messages.error(request, 'Select at least one row to approve.')
            else:
                try:
                    success, errs = _approve_pending_question_rows(conn, db_name, _get_pk_column(columns), ids)
                    if success:
                        messages.success(request, 'Approved %s row(s).' % success)
                    if errs:
                        for msg in errs[:10]:
                            messages.warning(request, msg)
                        if len(errs) > 10:
                            messages.warning(request, '… and %s more errors.' % (len(errs) - 10))
                except Exception as e:
                    messages.error(request, 'Approve failed: %s' % str(e))
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)

        if action == 'approve_edited' and db_alias == 'hsc' and table_name == 'cheradip_pending_question_request':
            pk_edit = (request.POST.get('pending_edit_id') or '').strip()
            if not pk_edit:
                messages.error(request, 'Missing pending row id.')
            else:
                try:
                    pk_col = _get_pk_column(columns)
                    column_types = _get_column_types(conn, table_name, db_name)
                    with conn.cursor() as cursor:
                        pk_esc = pk_col.replace('`', '``')
                        cursor.execute(
                            "SELECT * FROM `%s` WHERE `%s` = %%s" % (table_name.replace('`', '``'), pk_esc),
                            [pk_edit]
                        )
                        row_db = cursor.fetchone()
                    if not row_db:
                        messages.error(request, 'Row not found.')
                    else:
                        data = {}
                        for c in columns:
                            if c == pk_col:
                                continue
                            fk = 'field_%s' % c
                            if fk not in request.POST:
                                continue
                            val = request.POST.get(fk)
                            dt = column_types.get(c)
                            if dt in ('datetime', 'date'):
                                parsed = _parse_datetime_for_mysql(val)
                                if parsed is not None:
                                    val = parsed
                                elif val is not None and str(val).strip() == '':
                                    val = None
                            data[c] = val
                        if not data:
                            messages.error(request, 'No fields submitted.')
                        else:
                            _update_row(conn, table_name, columns, pk_col, pk_edit, data)
                            success, errs = _approve_pending_question_rows(conn, db_name, pk_col, [pk_edit])
                            if success:
                                messages.success(request, 'Edited and approved.')
                            if errs:
                                for msg in errs[:10]:
                                    messages.warning(request, msg)
                                if len(errs) > 10:
                                    messages.warning(request, '… and %s more errors.' % (len(errs) - 10))
                except Exception as e:
                    messages.error(request, 'Edit & approve failed: %s' % str(e))
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)

    # Filters for cheradip_pending_question_request (subject_tr, type, status)
    filter_subject_tr = (request.GET.get('filter_subject_tr') or '').strip()
    filter_type = (request.GET.get('filter_type') or '').strip()
    filter_status = (request.GET.get('filter_status') or '').strip()
    where_parts = []
    where_params = []
    if db_alias == 'hsc' and table_name == 'cheradip_pending_question_request':
        if filter_subject_tr:
            where_parts.append('subject_tr = %s')
            where_params.append(filter_subject_tr)
        if filter_type:
            where_parts.append('type = %s')
            where_params.append(filter_type)
        if filter_status:
            where_parts.append('status = %s')
            where_params.append(filter_status)
    where_clause = ' AND '.join(where_parts) if where_parts else None

    # Pagination
    page_num = request.GET.get('p', 1)
    try:
        page_num = max(1, int(page_num))
    except ValueError:
        page_num = 1
    total = _get_row_count(conn, table_name, where_clause=where_clause, where_params=where_params)
    paginator = Paginator(range(1), PAGE_SIZE)
    paginator._count = total
    offset = (page_num - 1) * PAGE_SIZE
    pk_column = _get_pk_column(columns)
    _, rows = _get_table_rows(conn, table_name, PAGE_SIZE, offset, pk_column, where_clause=where_clause, where_params=where_params)

    table_data_url = '/admin/databases/%s/%s/' % (db_alias, table_name)
    tables_url = '/admin/databases/%s/' % db_alias
    num_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    # For pending_question_request: reorder so qid, table, status appear after approved_at; show "qid" instead of "approved_qid"
    if db_alias == 'hsc' and table_name == 'cheradip_pending_question_request':
        PENDING_ORDER = (
            'id', 'level_tr', 'class_level', 'subject_tr', 'chapter_no', 'chapter', 'topic_no', 'topic',
            'question', 'option_1', 'option_2', 'option_3', 'option_4', 'answer', 'explanation', 'explanation2', 'explanation3',
            'type', 'level', 'subsource', 'created_at', 'approved_at', 'qid', 'table', 'status', 'requested_qid',
            'approved_qid', 'updated_by'
        )
        seen = set()
        ordered = []
        for c in PENDING_ORDER:
            if c in columns and c not in seen:
                seen.add(c)
                ordered.append(c)
        for c in columns:
            if c not in seen:
                ordered.append(c)
        columns = ordered
        display_columns = ['qid' if c == 'approved_qid' else c for c in columns]
        values_per_row = [([(r.get('qid') if c == 'approved_qid' else r.get(c)) for c in columns], r.get(pk_column)) for r in rows]
        row_list = [(list(zip(display_columns, vals)), rid) for vals, rid in values_per_row]
    else:
        display_columns = columns
        values_per_row = [([r.get(c) for c in columns], r.get(pk_column)) for r in rows]
        row_list = [(list(zip(display_columns, vals)), rid) for vals, rid in values_per_row]

    show_approve = (db_alias == 'hsc' and table_name == 'cheradip_pending_question_request')
    html_columns = ['question', 'option_1', 'option_2', 'option_3', 'option_4', 'explanation', 'explanation2', 'explanation3'] if show_approve else []
    filter_options = _get_pending_question_request_filter_options(conn, table_name) if show_approve else None
    from django.http import QueryDict
    q = request.GET.copy()
    q['p'] = page_num - 1
    prev_url = (table_data_url + '?' + q.urlencode()) if page_num > 1 else None
    q['p'] = page_num + 1
    next_url = (table_data_url + '?' + q.urlencode()) if page_num < num_pages else None
    context = {
        **admin.site.each_context(request),
        'title': 'Table: %s' % table_name,
        'db_alias': db_alias,
        'db_name': db_name,
        'db_label': label,
        'table_name': table_name,
        'columns': columns,
        'display_columns': display_columns,
        'pk_column': pk_column,
        'row_list': row_list,
        'total': total,
        'page_num': page_num,
        'num_pages': num_pages,
        'table_data_url': table_data_url,
        'prev_url': prev_url,
        'next_url': next_url,
        'tables_url': tables_url,
        'page_size': PAGE_SIZE,
        'show_approve': show_approve,
        'show_pending_filters': show_approve and filter_options is not None,
        'filter_options': filter_options,
        'filter_subject_tr': filter_subject_tr,
        'filter_type': filter_type,
        'filter_status': filter_status,
        'html_columns': html_columns,
    }
    return render(request, 'admin/database_table_data.html', context)


def _bulk_import(conn, table_name, columns, content, fmt, csv_has_header):
    """Import from CSV or JSON string. Returns number of rows inserted."""
    count = 0
    if fmt == 'json':
        data = json.loads(content)
        if not isinstance(data, list):
            data = [data]
        insert_cols = [c for c in columns if c != 'id']
        if not insert_cols:
            return 0
        placeholders = ', '.join(['%s'] * len(insert_cols))
        col_list = ', '.join('`%s`' % c.replace('`', '``') for c in insert_cols)
        sql = "INSERT INTO `%s` (%s) VALUES (%s)" % (table_name.replace('`', '``'), col_list, placeholders)
        with conn.cursor() as cursor:
            for row in data:
                if not isinstance(row, dict):
                    continue
                vals = [row.get(c) for c in insert_cols]
                try:
                    cursor.execute(sql, vals)
                    count += 1
                except Exception:
                    pass
        return count

    # CSV
    insert_cols = [c for c in columns if c != 'id']
    if not insert_cols:
        return 0
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return 0
    if csv_has_header:
        header = [h.strip().lower() for h in rows[0]]
        rows = rows[1:]
        col_indices = []
        for c in insert_cols:
            if c.lower() in header:
                col_indices.append(header.index(c.lower()))
            else:
                col_indices.append(-1)
    else:
        col_indices = list(range(len(insert_cols)))
    placeholders = ', '.join(['%s'] * len(insert_cols))
    col_list = ', '.join('`%s`' % c.replace('`', '``') for c in insert_cols)
    sql = "INSERT INTO `%s` (%s) VALUES (%s)" % (table_name.replace('`', '``'), col_list, placeholders)
    with conn.cursor() as cursor:
        for row in rows:
            if csv_has_header:
                vals = [row[col_indices[j]] if col_indices[j] >= 0 and col_indices[j] < len(row) else None for j in range(len(insert_cols))]
            else:
                vals = [row[j] if j < len(row) else None for j in range(len(insert_cols))]
            while len(vals) < len(insert_cols):
                vals.append(None)
            vals = vals[:len(insert_cols)]
            try:
                cursor.execute(sql, vals)
                count += 1
            except Exception:
                pass
    return count


@staff_member_required
def database_table_data_edit(request, db_alias, table_name, pk):
    """Edit a single row by primary key (id or first column)."""
    if db_alias not in connections:
        return HttpResponseNotFound('Unknown database alias.')
    table_name = table_name.strip().lower()
    if not _allowed_table_name(table_name):
        return HttpResponseBadRequest('Invalid table name.')
    conn = connections[db_alias]
    db_name = conn.settings_dict.get('NAME', db_alias)
    label = dict(DATABASE_MENU).get(db_alias, db_alias)
    columns = _get_table_columns(conn, table_name)
    if not columns:
        return HttpResponseNotFound('Table not found.')
    pk_column = _get_pk_column(columns)
    column_types = _get_column_types(conn, table_name, db_name)

    with conn.cursor() as cursor:
        pk_esc = pk_column.replace('`', '``')
        cursor.execute(
            "SELECT * FROM `%s` WHERE `%s` = %%s" % (table_name.replace('`', '``'), pk_esc),
            [pk]
        )
        row = cursor.fetchone()
    if not row:
        return HttpResponseNotFound('Row not found.')
    row_data = dict(zip(columns, row))

    if request.method == 'POST':
        data = {c: request.POST.get('field_%s' % c) for c in columns}
        for c in columns:
            dt = column_types.get(c)
            if dt in ('datetime', 'date'):
                parsed = _parse_datetime_for_mysql(data.get(c))
                if parsed is not None:
                    data[c] = parsed
                elif data.get(c) is not None and str(data.get(c)).strip() == '':
                    data[c] = None
        try:
            _update_row(conn, table_name, columns, pk_column, pk, data)
            messages.success(request, 'Row updated.')
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)
        except Exception as e:
            messages.error(request, 'Update failed: %s' % str(e))

    table_data_url = '/admin/databases/%s/%s/' % (db_alias, table_name)
    row_items = [(c, _format_cell_for_edit(row_data.get(c), column_types.get(c))) for c in columns]
    context = {
        **admin.site.each_context(request),
        'title': 'Edit row: %s' % table_name,
        'db_alias': db_alias,
        'db_label': label,
        'table_name': table_name,
        'columns': columns,
        'row_items': row_items,
        'pk': pk,
        'pk_column': pk_column,
        'table_data_url': table_data_url,
    }
    return render(request, 'admin/database_table_data_edit.html', context)
