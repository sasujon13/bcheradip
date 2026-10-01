"""
Group Django Admin index by database: Cheradip (default), HSC, Honours, Job.
Each section shows Django models plus all DB tables (same layout; tables link to table-data view).
"""
import re
from django.contrib import admin
from django.db import connections, router
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.text import capfirst


# Order and display names (no "All" in UI)
DATABASE_SECTIONS = [
    ('default', 'Cheradip'),
    ('hsc', 'HSC'),
    ('honours', 'Honours'),
    ('job', 'Job'),
    ('childcare', 'Child Care'),
    ('ecommerce', 'eCommerce'),
]

# For backward compatibility if something passed db=all
VALID_DB_ALIASES = {alias for alias, _ in DATABASE_SECTIONS}


def build_db_tabs_for_index(active_alias, use_databases_path=False, settings_active=False, settings_url=None):
    """Build tab list for the index UI. use_databases_path: True for /admin/databases/<alias>/ URLs. settings_active: True when on Settings page. settings_url: optional custom Settings tab URL (e.g. the global JSON settings page /admin/settings/)."""
    tabs = []
    for alias, name in DATABASE_SECTIONS:
        if use_databases_path:
            url = f'/admin/databases/{alias}/'
        else:
            url = f'/admin?db={alias}'
        tabs.append({'alias': alias, 'name': name, 'url': url, 'active': (alias == active_alias and not settings_active)})
    # Settings tab: show on both /admin?db=... and /admin/databases/<alias>/; link to Settings page for current DB
    tabs.append({
        'alias': 'settings',
        'name': 'Settings',
        'url': settings_url or f'/admin/databases/{active_alias}/settings/',
        'active': settings_active,
    })
    return tabs


def _allowed_table_name(name):
    n = (name or "").strip().lower()
    return bool(n and re.match(r'^(cheradip_[a-z0-9_]+|cc_[a-z0-9_]+|ecommerce_[a-z0-9_]+|django_migrations)$', n))


def _table_notification_count(conn, table_name):
    """Return a compact activity/action count for the circle beside an admin table."""
    safe_table = table_name.replace('`', '``')
    try:
        with conn.cursor() as cursor:
            columns = {column.name for column in conn.introspection.get_table_description(cursor, table_name)}
            special_filters = {
                'cheradip_pending_question_request': ("`status` IN ('pending','new')", 'status'),
                'ecommerce_order': ("`status` IN ('pending','confirmed','processing')", 'status'),
                'ecommerce_payment': ("`status` = 'pending'", 'status'),
                'ecommerce_notification': ("`is_read` = 0", 'is_read'),
                'ecommerce_product_variant': ("`is_active` = 1 AND `stock` <= `low_stock_threshold`", 'stock'),
                'ecommerce_review': ("`is_approved` = 0", 'is_approved'),
                'ecommerce_import_job': ("`status` IN ('processing','failed')", 'status'),
            }
            special = special_filters.get(table_name)
            if special and special[1] in columns:
                cursor.execute(f"SELECT COUNT(*) FROM `{safe_table}` WHERE {special[0]}")
                return int(cursor.fetchone()[0] or 0)
            timestamp = next((name for name in ('updated_at', 'modified_at', 'created_at') if name in columns), None)
            if timestamp:
                cursor.execute(
                    f"SELECT COUNT(*) FROM `{safe_table}` WHERE `{timestamp}` >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
                )
                return int(cursor.fetchone()[0] or 0)
    except Exception:
        return 0
    return 0


def get_current_db(request, force_db=None):
    """Return the selected database alias. Uses force_db if set, else request GET (?db=). Default 'default'."""
    if force_db is not None and force_db in VALID_DB_ALIASES:
        return force_db
    db = (request.GET.get('db') or 'default').lower()
    if db not in VALID_DB_ALIASES:
        return 'default'
    return db


def get_app_list_by_database(request, app_label=None, force_db=None):
    """
    Return app_list for the selected database (?db= or force_db).
    One section; models + introspected tables for that DB.
    """
    site = admin.site
    current_db = get_current_db(request, force_db=force_db)
    if current_db == 'all':
        current_db = 'default'
    # Bucket: db_alias -> list of model_dict
    db_models = {db_alias: [] for db_alias, _ in DATABASE_SECTIONS}

    for model, model_admin in site._registry.items():
        if app_label is not None and model._meta.app_label != app_label:
            continue
        if not model_admin.has_module_permission(request):
            continue
        perms = model_admin.get_model_perms(request)
        if not any(perms.values()):
            continue

        db = router.db_for_read(model) or 'default'
        if db not in db_models:
            db = 'default'

        info = (model._meta.app_label, model._meta.model_name)
        model_dict = {
            'model': model,
            'name': capfirst(model._meta.verbose_name_plural),
            'object_name': model._meta.object_name,
            'perms': perms,
            'admin_url': None,
            'add_url': None,
            'update_count': 0,
        }
        if perms.get('change') or perms.get('view'):
            model_dict['view_only'] = not perms.get('change')
        try:
            model_dict['admin_url'] = reverse(
                'admin:%s_%s_changelist' % info,
                current_app=site.name,
            )
        except NoReverseMatch:
            pass
        if perms.get('add'):
            try:
                model_dict['add_url'] = reverse(
                    'admin:%s_%s_add' % info,
                    current_app=site.name,
                )
            except NoReverseMatch:
                pass

        db_models[db].append(model_dict)

    # Selected DB = models + all introspected tables (same design)
    models = db_models.get(current_db, [])
    # Only show registered models whose table actually exists in this database
    existing_tables = set()
    if current_db in connections:
        try:
            conn = connections[current_db]
            with conn.cursor() as cursor:
                existing_tables = set(conn.introspection.table_names(cursor))
        except Exception:
            pass
    models = [m for m in models if m.get('model') is None or (hasattr(m['model'], '_meta') and m['model']._meta.db_table in existing_tables)]
    if current_db in connections:
        for model_dict in models:
            model = model_dict.get('model')
            if model is not None and hasattr(model, '_meta'):
                model_dict['update_count'] = _table_notification_count(connections[current_db], model._meta.db_table)
    shown_tables = set()
    for m in models:
        mod = m.get('model')
        if mod is not None and hasattr(mod, '_meta'):
            shown_tables.add(mod._meta.db_table)
    # Add every table from this DB that isn't a registered model (same layout: Add / Change -> table data)
    if current_db in connections and existing_tables:
        try:
            for table in sorted(existing_tables):
                if not _allowed_table_name(table):
                    continue
                if table in shown_tables:
                    continue
                table_data_url = reverse(
                    'admin:database_table_data',
                    kwargs={'db_alias': current_db, 'table_name': table},
                    current_app=site.name,
                )
                models.append({
                    'model': None,
                    'name': table,
                    'object_name': table,
                    'perms': {'add': True, 'change': True, 'view': True, 'delete': True},
                    'admin_url': table_data_url,
                    'add_url': table_data_url,
                    'view_only': False,
                    'update_count': _table_notification_count(conn, table),
                })
        except Exception:
            pass
    models.sort(key=lambda x: x['name'].lower())
    # Default (Cheradip) database: expose the global JSON settings page as a
    # pseudo "table" so clicking "settings" on /admin/ opens /admin/settings/.
    if current_db == 'default':
        site_name = admin.site.name
        try:
            settings_url = reverse('admin:site_settings', current_app=site_name)
        except NoReverseMatch:
            settings_url = '/admin/settings/'
        models.insert(0, {
            'model': None,
            'name': 'settings',
            'object_name': 'settings',
            'perms': {'add': True, 'change': True, 'view': True, 'delete': False},
            'admin_url': settings_url,
            'add_url': settings_url,
            'view_only': False,
            'update_count': 0,
        })
    section_name = dict(DATABASE_SECTIONS).get(current_db, current_db)

    app_list = [{
        'name': section_name,
        'app_label': 'cheradip',
        'app_url': reverse('admin:index', current_app=site.name),
        'has_module_perms': True,
        'models': models,
    }]
    return app_list
