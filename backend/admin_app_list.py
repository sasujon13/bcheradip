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
]

# For backward compatibility if something passed db=all
VALID_DB_ALIASES = {alias for alias, _ in DATABASE_SECTIONS}


def build_db_tabs_for_index(active_alias, use_databases_path=False):
    """Build tab list for the index UI. use_databases_path: True for /admin/databases/<alias>/ URLs."""
    tabs = []
    for alias, name in DATABASE_SECTIONS:
        if use_databases_path:
            url = f'/admin/databases/{alias}/'
        else:
            url = f'/admin?db={alias}'
        tabs.append({'alias': alias, 'name': name, 'url': url, 'active': (alias == active_alias)})
    return tabs


def _allowed_table_name(name):
    return bool(name and re.match(r'^cheradip_[a-z0-9_]+$', name.strip().lower()))


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
                })
        except Exception:
            pass
    models.sort(key=lambda x: x['name'].lower())
    section_name = dict(DATABASE_SECTIONS).get(current_db, current_db)

    app_list = [{
        'name': section_name,
        'app_label': 'cheradip',
        'app_url': reverse('admin:index', current_app=site.name),
        'has_module_perms': True,
        'models': models,
    }]
    return app_list
