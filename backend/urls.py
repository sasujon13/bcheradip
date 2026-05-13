from django.contrib import admin
from django.urls import path, re_path, include
from django.template.response import TemplateResponse
from django.conf import settings
from django.views.static import serve

# Add custom admin views: Databases list and Tables per database
from backend import database_admin_views

# Branding: title, site name, favicon and teal theme are in templates/admin/base_site.html
admin.site.site_header = getattr(settings, 'ADMIN_SITE_HEADER', 'Cheradip Administration')
admin.site.site_title = getattr(settings, 'ADMIN_SITE_TITLE', 'admin')
admin.site.index_title = 'Cheradip administration'
from backend.admin_app_list import get_app_list_by_database, get_current_db, DATABASE_SECTIONS, build_db_tabs_for_index

_original_admin_get_urls = admin.site.get_urls
_original_get_app_list = admin.site.get_app_list
_original_index = admin.site.index


def _admin_get_urls_with_databases():
    from django.urls import path
    urls = _original_admin_get_urls()
    custom = [
        path('databases/', admin.site.admin_view(database_admin_views.databases_list), name='databases_list'),
        path('databases/<str:db_alias>/', admin.site.admin_view(database_admin_views.database_tables), name='database_tables'),
        path('databases/<str:db_alias>/settings/', admin.site.admin_view(database_admin_views.database_settings), name='database_settings'),
        path('databases/<str:db_alias>/<str:table_name>/', admin.site.admin_view(database_admin_views.database_table_data), name='database_table_data'),
        path('databases/<str:db_alias>/<str:table_name>/edit/<path:pk>/', admin.site.admin_view(database_admin_views.database_table_data_edit), name='database_table_data_edit'),
    ]
    return custom + urls


def _admin_get_app_list(request, app_label=None):
    """Show only the selected database's models (?db=default|hsc|honours|job)."""
    return get_app_list_by_database(request, app_label=app_label)


def _admin_index(request, extra_context=None):
    """Index with horizontal database tabs; content shows tables for selected DB."""
    current_db = get_current_db(request)
    db_tabs = build_db_tabs_for_index(active_alias=current_db, use_databases_path=False)
    context = {
        **admin.site.each_context(request),
        'title': admin.site.index_title,
        'subtitle': None,
        'app_list': admin.site.get_app_list(request),
        'db_tabs': db_tabs,
        'current_db': current_db,
        'table_links_only': True,
        **(extra_context or {}),
    }
    request.current_app = admin.site.name
    return TemplateResponse(
        request,
        admin.site.index_template or 'admin/index.html',
        context,
    )


admin.site.get_urls = _admin_get_urls_with_databases
admin.site.get_app_list = _admin_get_app_list
admin.site.index = _admin_index

urlpatterns = [
    # Project-root favicon (bcheradip/favicon.ico); fixes tab icon and /favicon.ico requests.
    re_path(
        r'^favicon\.ico$',
        serve,
        {'document_root': settings.BASE_DIR, 'path': 'favicon.ico'},
    ),
    path('admin/', admin.site.urls),
    path('api/', include('cheradip.urls')),
    path('', include('cheradip.urls')),  # keep root for backward compatibility
]

# Ensure /static/ admin CSS/JS resolve in DEBUG (e.g. custom runserver or URL layout quirks).
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns

    urlpatterns += staticfiles_urlpatterns()


