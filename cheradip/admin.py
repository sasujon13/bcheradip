"""
Admin for cheradip default-DB models only.
Tables: Country, Location, Item, Transaction, OrderDetail, Customer, CustomerToken, Notification, JsonData.
"""
from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.contrib.admin.views.decorators import staff_member_required
from .models import (
    Country,
    Location,
    Item,
    Transaction,
    OrderDetail,
    Customer,
    CustomerToken,
    Notification,
    JsonData
)


def _get_table_structure(table_name):
    """Return list of {name, type, required} for the given DB table (from information_schema)."""
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, COLUMN_KEY
            FROM information_schema.COLUMNS
            WHERE table_schema = DATABASE() AND table_name = %s
            ORDER BY ORDINAL_POSITION
        """, [table_name])
        rows = cur.fetchall()
    out = []
    for col_name, data_type, max_len, nullable, key in rows:
        req = (nullable or '').upper() != 'YES' and (key or '') == 'PRI'
        hint = data_type or ''
        if max_len:
            hint += f'({max_len})'
        out.append({'name': col_name, 'type': hint, 'required': req})
    return out


def _load_rows_from_upload(upload, fmt, encoding='utf-8'):
    """Parse uploaded file to list of dicts. fmt in ('csv','json')."""
    import csv
    import json
    raw = upload.read() if hasattr(upload, 'read') else upload
    if isinstance(raw, bytes):
        raw = raw.decode(encoding, errors='replace')
    if fmt == 'json':
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ('rows', 'data', 'subjects'):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []
    # CSV
    import io
    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)


def import_csv_json_view_for_model(model):
    """Factory: returns a view for bulk CSV/JSON import for the given model."""
    from django.db import IntegrityError

    @staff_member_required
    def view(request):
        changelist_url = reverse('admin:%s_%s_changelist' % (model._meta.app_label, model._meta.model_name))
        table_name = model._meta.db_table
        table_structure = _get_table_structure(table_name)
        if request.method == 'POST':
            upload = request.FILES.get('bulk_file')
            fmt = (request.POST.get('format') or 'csv').strip().lower()
            if not upload:
                from django.contrib import messages
                messages.error(request, 'Please select a file.')
                return redirect(changelist_url)
            try:
                rows = _load_rows_from_upload(upload, fmt, encoding='utf-8')
            except Exception as e:
                from django.contrib import messages
                messages.error(request, f'Could not parse file: {e}')
                return redirect(changelist_url)
            if not rows:
                from django.contrib import messages
                messages.warning(request, 'No rows found in file.')
                return redirect(changelist_url)
            created = errors = 0
            for row in rows:
                row_norm = {str(k).strip().lower().replace(' ', '_'): v for k, v in (row or {}).items()}
                kwargs = {}
                for f in model._meta.get_fields():
                    if not hasattr(f, 'column') or f.many_to_many or f.auto_created:
                        continue
                    if getattr(f, 'auto_now', False) or getattr(f, 'auto_now_add', False):
                        continue
                    if getattr(f, 'primary_key', False) and getattr(f, 'get_internal_type', lambda: '')() == 'AutoField':
                        continue
                    key = None
                    for rk in (getattr(f, 'column', None) or f.name, f.name):
                        if rk and rk.lower().replace(' ', '_') in row_norm:
                            key = rk.lower().replace(' ', '_')
                            break
                    if key is not None:
                        val = row_norm.get(key)
                        if val is not None and str(val).strip() != '':
                            val = str(val).strip() if isinstance(val, str) else val
                            if hasattr(f, 'get_internal_type'):
                                it = f.get_internal_type()
                                if it in ('AutoField', 'IntegerField', 'BigIntegerField', 'SmallIntegerField', 'PositiveIntegerField', 'PositiveSmallIntegerField', 'ForeignKey'):
                                    try:
                                        val = int(float(val))
                                    except (ValueError, TypeError):
                                        pass
                                elif it in ('FloatField', 'DecimalField'):
                                    try:
                                        val = float(val)
                                    except (ValueError, TypeError):
                                        pass
                                elif it == 'BooleanField':
                                    val = str(val).lower() in ('1', 'true', 'yes', 'on')
                            kwargs[f.name] = val
                        elif f.null or f.blank:
                            kwargs[f.name] = None
                try:
                    model.objects.create(**kwargs)
                    created += 1
                except (IntegrityError, ValueError, TypeError) as e:
                    errors += 1
            from django.contrib import messages
            messages.success(request, f'Import done: {created} created, {errors} error(s).')
            return redirect(changelist_url)
        context = {
            'title': 'Import (CSV/JSON)',
            'opts': model._meta,
            'changelist_url': changelist_url,
            'table_structure': table_structure,
            'table_name': table_name,
        }
        return render(request, 'admin/cheradip/import_csv_json.html', context)
    return view


class BulkImportCsvJsonMixin:
    """Mixin: add 'Import (CSV/JSON)' link and view for bulk import."""
    change_list_template = 'admin/cheradip/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        name = '%s_%s_import_csv_json' % (self.model._meta.app_label, self.model._meta.model_name)
        return [path('import-csv-json/', import_csv_json_view_for_model(self.model), name=name)] + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_csv_json_url'] = reverse(
            'admin:%s_%s_import_csv_json' % (self.model._meta.app_label, self.model._meta.model_name)
        )
        return super().changelist_view(request, extra_context)


# -----------------------------------------------------------------------------
# Register only default-DB models (ensure_cheradip tables)
# -----------------------------------------------------------------------------

@admin.register(Country)
class CountryAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('country_code', 'country_name', 'phone_code', 'is_active', 'display_order')
    search_fields = ('country_code', 'country_name', 'country_name_native', 'phone_code')
    list_filter = ('is_active', 'is_featured', 'continent')
    ordering = ('display_order', 'country_name')


@admin.register(Location)
class LocationAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'country', 'division', 'district', 'thana')
    search_fields = ('division', 'district', 'thana', 'local_address')
    list_filter = ('country',)


admin.site.register(Item)
admin.site.register(OrderDetail)
admin.site.register(JsonData)


@admin.register(Customer)
class CustomerAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('username', 'fullName', 'acctype', 'group', 'email', 'is_active', 'date_joined')
    search_fields = ('username', 'fullName', 'email', 'division', 'district')
    list_filter = ('acctype', 'group', 'gender', 'is_active', 'date_joined')
    readonly_fields = ('date_joined', 'last_login', 'updated_at')


@admin.register(CustomerToken)
class CustomerTokenAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('key', 'customer', 'created', 'expires_at')
    search_fields = ('key', 'customer__username', 'customer__fullName')
    list_filter = ('created', 'expires_at')
    readonly_fields = ('key', 'created')


@admin.register(Transaction)
class TransactionAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('trxid', 'username', 'paidFrom', 'Paid', 'payment_method', 'status', 'created_at')
    search_fields = ('trxid', 'username')
    list_filter = ('status', 'payment_method', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Notification)
class NotificationAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'text', 'link')
    search_fields = ('text', 'link')


# Re-register Item, OrderDetail, JsonData with bulk import mixin
class ItemAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    pass


class OrderDetailAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    pass


class JsonDataAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    pass


admin.site.unregister(Item)
admin.site.unregister(OrderDetail)
admin.site.unregister(JsonData)
admin.site.register(Item, ItemAdmin)
admin.site.register(OrderDetail, OrderDetailAdmin)
admin.site.register(JsonData, JsonDataAdmin)
