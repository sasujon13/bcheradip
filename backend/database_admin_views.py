"""
Custom Django Admin views: list databases, list tables per database,
and browse/add/delete/edit rows + bulk import CSV/JSON for any table.
"""
import csv
import io
import json
import re
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.template.response import TemplateResponse
from django.db import connections
from django.urls import reverse

from backend.admin_app_list import get_app_list_by_database, build_db_tabs_for_index
from django.core.paginator import Paginator
from django.http import HttpResponseNotFound, HttpResponseBadRequest
from django.contrib import messages


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


def _get_row_count(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM `%s`" % table_name.replace('`', '``'))
        return cursor.fetchone()[0]


def _get_table_rows(conn, table_name, limit, offset, order_by_column):
    """order_by_column: column name for ORDER BY (e.g. id or first column)."""
    order_col = order_by_column.replace('`', '``')
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM `%s` ORDER BY `%s` LIMIT %%s OFFSET %%s" % (table_name.replace('`', '``'), order_col),
            [limit, offset]
        )
        columns = [row[0] for row in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return columns, rows


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

    # Pagination
    page_num = request.GET.get('p', 1)
    try:
        page_num = max(1, int(page_num))
    except ValueError:
        page_num = 1
    total = _get_row_count(conn, table_name)
    paginator = Paginator(range(1), PAGE_SIZE)
    paginator._count = total
    offset = (page_num - 1) * PAGE_SIZE
    pk_column = _get_pk_column(columns)
    _, rows = _get_table_rows(conn, table_name, PAGE_SIZE, offset, pk_column)

    table_data_url = '/admin/databases/%s/%s/' % (db_alias, table_name)
    tables_url = '/admin/databases/%s/' % db_alias
    num_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    row_list = [([r.get(c) for c in columns], r.get(pk_column)) for r in rows]

    context = {
        **admin.site.each_context(request),
        'title': 'Table: %s' % table_name,
        'db_alias': db_alias,
        'db_name': db_name,
        'db_label': label,
        'table_name': table_name,
        'columns': columns,
        'pk_column': pk_column,
        'row_list': row_list,
        'total': total,
        'page_num': page_num,
        'num_pages': num_pages,
        'table_data_url': table_data_url,
        'tables_url': tables_url,
        'page_size': PAGE_SIZE,
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
    label = dict(DATABASE_MENU).get(db_alias, db_alias)
    columns = _get_table_columns(conn, table_name)
    if not columns:
        return HttpResponseNotFound('Table not found.')
    pk_column = _get_pk_column(columns)

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
        try:
            _update_row(conn, table_name, columns, pk_column, pk, data)
            messages.success(request, 'Row updated.')
            return redirect('admin:database_table_data', db_alias=db_alias, table_name=table_name)
        except Exception as e:
            messages.error(request, 'Update failed: %s' % str(e))

    table_data_url = '/admin/databases/%s/%s/' % (db_alias, table_name)
    row_items = [(c, row_data.get(c)) for c in columns]
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
