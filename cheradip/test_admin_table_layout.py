from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.contrib.auth.models import AnonymousUser


class AdminTableLayoutTests(SimpleTestCase):
    def test_module_headings_keep_requested_colour_and_padding_without_forced_background(self):
        html = render_to_string('admin/index.html', self.context())
        rule = html.split('.module h2, .module caption, .inline-group h2 {', 1)[1].split('}', 1)[0]
        import re
        active = re.sub(r'/\*.*?\*/', '', rule, flags=re.S)
        self.assertNotIn('background:', active)
        self.assertIn('color: var(--header-on-primary) !important;', active)
        self.assertIn('padding: 7px;', active)

    def context(self, table_links_only=False):
        request = RequestFactory().get('/admin/')
        request.user = AnonymousUser()
        return {
            'request': request, 'user': request.user, 'has_permission': False,
            'scraper_frontend_url': '/scraper', 'commerce_frontend_url': '/ecommerce/manage',
            'site_url': '/', 'site_title': 'admin',
            'site_header': 'Cheradip Administration', 'subtitle': '',
            'title': 'Tables', 'is_popup': False, 'is_nav_sidebar_enabled': True,
            'available_apps': [], 'db_tabs': [], 'table_links_only': table_links_only,
            'app_list': [{
                'app_label': 'cheradip', 'app_url': '/admin/cheradip/',
                'name': 'Cheradip', 'has_module_perms': True,
                'models': [{
                    'object_name': 'Customer', 'name': 'Customers',
                    'admin_url': '/admin/cheradip/customer/',
                    'add_url': '/admin/cheradip/customer/add/', 'update_count': 3,
                    'perms': {'add': True, 'change': True, 'view': True},
                }],
            }],
        }

    def test_model_catalog_loads_shared_fluid_styles_and_keeps_actions(self):
        html = render_to_string('admin/index.html', self.context())
        self.assertIn('admin/css/table_catalog.css', html)
        self.assertIn('admin/js/table_catalog.js', html)
        self.assertIn('admin/js/table_loading.js', html)
        self.assertIn('admin/css/table_loading.css', html)
        self.assertIn('id="admin-table-loading"', html)
        self.assertIn('aria-label="Loading Tables…"', html)
        self.assertIn('/admin/cheradip/customer/', html)
        self.assertIn('/admin/cheradip/customer/add/', html)
        self.assertNotIn('repeat(6, minmax(0, 1fr))', html)

    def test_database_catalog_preserves_table_links_and_update_markers(self):
        html = render_to_string('admin/index.html', self.context(table_links_only=True))
        self.assertIn('admin-tables-grid', html)
        self.assertIn('/admin/cheradip/customer/', html)
        self.assertIn('table-update-badge', html)
        self.assertIn('>3</span>', html)

    def test_raw_table_directory_uses_shared_layout_without_fixed_columns(self):
        context = self.context()
        context.update(db_alias='default', db_label='Cheradip', db_name='cheradip',
                       table_list=['short', 'a_very_long_database_table_name'])
        html = render_to_string('admin/database_tables.html', context)
        self.assertIn('admin/js/table_catalog.js', html)
        self.assertIn('class="table-list"', html)
        self.assertIn('title="a_very_long_database_table_name"', html)
        self.assertNotIn('column-count:', html)

    def test_catalog_rules_do_not_select_record_tables_or_duplicate_inline_layouts(self):
        from pathlib import Path
        from django.conf import settings
        root = Path(settings.BASE_DIR)
        script = (root / 'static_src/admin/js/table_catalog.js').read_text(encoding='utf-8')
        self.assertIn('.module[class*="app-"] table > tbody', script)
        self.assertNotIn('#content-main .module table > tbody', script)
        self.assertIn('ResizeObserver', script)
        self.assertIn('MutationObserver', script)
        self.assertIn('document.fonts.ready', script)
        css = (root / 'static_src/admin/css/table_catalog.css').read_text(encoding='utf-8')
        self.assertIn('repeat(auto-fit, minmax(min(100%, var(--table-catalog-column-width, 20rem)), 1fr))', css)
        self.assertIn('max-height: var(--table-catalog-height', css)
        self.assertIn('scrollbar-gutter: stable', css)
        for name in ('index.html', 'database_table_data.html'):
            template = (root / 'templates/admin' / name).read_text(encoding='utf-8')
            self.assertNotIn('grid-template-columns:', template)
