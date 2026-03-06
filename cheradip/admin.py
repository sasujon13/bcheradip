from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib.admin.views.decorators import staff_member_required
from .models import (
    Institutes, Item, Token, Banbeis, Recommend, Recommend5, Recommend6, 
    Vacancy, Vacancy5, Vacancy6, Merit, Merit5, Merit6, Customer,
    CustomerToken, Order, Ordered, Canceled, OrderDetail, Transaction, 
    Group, Subject, Chapter, Topic, Mcq_ict, Notification, Institute, Year, JsonData,
    PendingSubjectRequest,
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


def _get_subject_table_structure():
    """Return table structure for cheradip_subject."""
    return _get_table_structure('cheradip_subject')


def _load_rows_from_upload(upload, fmt, encoding='utf-8'):
    """Parse uploaded file to list of dicts. fmt in ('csv','json'). Accepts JSON list or {'rows': [...]} / {'data': [...]}."""
    from cheradip.management.commands.import_degree_subjects_bulk import (
        load_rows_from_csv_file,
        load_rows_from_json_file,
    )
    if fmt == 'json':
        import json
        raw = upload.read() if hasattr(upload, 'read') else upload
        if isinstance(raw, bytes):
            raw = raw.decode(encoding, errors='replace')
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ('rows', 'data', 'subjects'):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []
    return load_rows_from_csv_file(upload, encoding=encoding or 'utf-8-sig')


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


@staff_member_required
def import_subject_csv_json_view(request):
    """Admin: Import (CSV/JSON) – upload file; show cheradip_subject column structure as guidance."""
    from cheradip.management.commands.import_degree_subjects_bulk import (
        load_rows_from_csv_file,
        load_rows_from_json_file,
        import_degree_subjects,
    )
    changelist_url = reverse('admin:cheradip_subject_changelist')
    table_structure = _get_subject_table_structure()
    if request.method == 'POST':
        upload = request.FILES.get('bulk_file')
        fmt = (request.POST.get('format') or 'csv').strip().lower()
        country = (request.POST.get('country') or 'BD').strip()[:2] or 'BD'
        if not upload:
            from django.contrib import messages
            messages.error(request, 'Please select a file.')
            return redirect(changelist_url)
        try:
            if fmt == 'json':
                rows = load_rows_from_json_file(upload, encoding='utf-8')
            else:
                rows = load_rows_from_csv_file(upload, encoding='utf-8-sig')
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f'Could not parse file: {e}')
            return redirect(changelist_url)
        if not rows:
            from django.contrib import messages
            messages.warning(request, 'No rows found in file.')
            return redirect(changelist_url)
        created, updated, skipped = import_degree_subjects(rows, country_default=country)
        from django.contrib import messages
        messages.success(request, f'Import done: {created} created, {updated} updated, {skipped} skipped.')
        return redirect(changelist_url)
    context = {
        'title': 'Import (CSV/JSON)',
        'opts': Subject._meta,
        'changelist_url': changelist_url,
        'table_structure': table_structure,
    }
    return render(request, 'admin/cheradip/subject/import_csv_json.html', context)


class BulkImportCsvJsonMixin:
    """Mixin: add 'Import (CSV/JSON)' link and view for bulk import."""
    change_list_template = 'admin/cheradip/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        name = '%s_%s_import_csv_json' % (self.model._meta.app_label, self.model._meta.model_name)
        if self.model == Subject:
            view = import_subject_csv_json_view
        else:
            view = import_csv_json_view_for_model(self.model)
        return [path('import-csv-json/', view, name=name)] + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_csv_json_url'] = reverse(
            'admin:%s_%s_import_csv_json' % (self.model._meta.app_label, self.model._meta.model_name)
        )
        return super().changelist_view(request, extra_context)


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


@admin.register(Order)
class OrderAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'username', 'fullName', 'status', 'paymentMethod', 'shipped', 'created_at')
    search_fields = ('username', 'fullName', 'district', 'thana')
    list_filter = ('status', 'paymentMethod', 'shipped', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Ordered)
class OrderedAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'username', 'fullName', 'status', 'shipped', 'delivered_at', 'created_at')
    search_fields = ('username', 'fullName', 'district')
    list_filter = ('status', 'shipped', 'delivered_at', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'delivered_at')


@admin.register(Canceled)
class CanceledAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'username', 'fullName', 'shipped', 'cancelled_at', 'created_at')
    search_fields = ('username', 'fullName', 'cancellation_reason')
    list_filter = ('shipped', 'cancelled_at', 'created_at')
    readonly_fields = ('created_at', 'cancelled_at')

@admin.register(Token)
class TokenAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('Token','Counter',)
    search_fields = ('Token','Counter',)

@admin.register(Banbeis)
class BanbeisAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('EIIN','Mouza',)
    search_fields = ('EIIN','Mouza',)

@admin.register(Recommend)
class RecommendAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'EIIN', 'Name', 'Roll', 'Subject', 'Rank')
    search_fields = ('EIIN', 'Name', 'Roll', 'Subject', 'District', 'Thana')
    list_filter = ('Subject', 'District')


@admin.register(Recommend5)
class Recommend5Admin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'EIIN', 'Name', 'Roll', 'Subject', 'Rank')
    search_fields = ('EIIN', 'Name', 'Roll', 'Subject', 'District', 'Thana')


@admin.register(Recommend6)
class Recommend6Admin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'EIIN', 'Name', 'Roll', 'Subject', 'Rank')
    search_fields = ('EIIN', 'Name', 'Roll', 'Subject', 'District', 'Thana')

@admin.register(Merit)
class MeritAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')
    search_fields = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')

@admin.register(Merit5)
class Merit5Admin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')
    search_fields = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')

@admin.register(Merit6)
class Merit6Admin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')
    search_fields = ('Code', 'Name', 'Batch', 'Roll', 'Mark', 'Rank', 'SL', 'Subject')

@admin.register(Vacancy)
class VacancyAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject', 'Vacancy')
    search_fields = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject')

@admin.register(Vacancy5)
class Vacancy5Admin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject', 'Vacancy')
    search_fields = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject')

@admin.register(Vacancy6)
class Vacancy6Admin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject', 'Vacancy')
    search_fields = ('EIIN', 'Name', 'District', 'Thana', 'Designation', 'Subject')

@admin.register(Group)
class GroupAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('group_code', 'group_name', 'group_name_bn', 'created_at')
    search_fields = ('group_code', 'group_name', 'group_name_bn')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Notification)
class NotificationAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'text', 'link')
    search_fields = ('text', 'link')


# Re-register Item, OrderDetail, JsonData with bulk import
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


@admin.register(Subject)
class SubjectAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'level', 'level_tr', 'groups', 'get_class_display', 'subject_name', 'subject_translated', 'subject_code', 'country_id', 'language_code', 'created_at', 'updated_at')
    search_fields = ('subject_code', 'subject_name', 'subject_translated', 'level', 'level_tr')
    list_filter = ('country_id', 'language_code', 'level', 'class_level')
    readonly_fields = ('created_at', 'updated_at')


def _generate_degree_subject_code(subject_translated, country_id):
    """Generate unique subject_code for Degree subject (max 12 chars)."""
    import re
    from django.db import connection
    base = (subject_translated or '').strip()[:15]
    base = re.sub(r'[^a-zA-Z0-9]', '_', base).upper() or 'SUB'
    cid = (country_id or 'BD')[:2]
    with connection.cursor() as cur:
        for suffix in range(1, 1000):
            if suffix == 1:
                code = f'DEG_{base[:6]}_{cid}'[:12]
            else:
                code = f'DEG_{base[:4]}_{cid}{suffix}'[:12]
            cur.execute('SELECT 1 FROM cheradip_subject WHERE subject_code = %s', [code])
            if not cur.fetchone():
                return code
    import hashlib
    h = hashlib.md5((str(subject_translated) + str(country_id)).encode()).hexdigest()[:4].upper()
    return f'DEG_{h}_BD'[:12]


def _generate_honours_subject_code(subject_translated, country_id):
    """Generate unique subject_code in honours.cheradip_subject (max 12 chars)."""
    import re
    import json
    from django.db import connections
    conn = connections['honours']
    base = (subject_translated or '').strip()[:15]
    base = re.sub(r'[^a-zA-Z0-9]', '_', base).upper() or 'SUB'
    cid = (country_id or 'BD')[:2]
    with conn.cursor() as cur:
        for suffix in range(1, 1000):
            if suffix == 1:
                code = f'HON_{base[:6]}_{cid}'[:12]
            else:
                code = f'HON_{base[:4]}_{cid}{suffix}'[:12]
            cur.execute('SELECT 1 FROM cheradip_subject WHERE subject_code = %s', [code])
            if not cur.fetchone():
                return code
    import hashlib
    h = hashlib.md5((str(subject_translated) + str(country_id)).encode()).hexdigest()[:4].upper()
    return f'HON_{h}_{cid}'[:12]


@admin.register(PendingSubjectRequest)
class PendingSubjectRequestAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'subject_name', 'subject_translated', 'degree_type', 'country_id', 'status', 'created_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('status', 'country_id', 'created_at')
    search_fields = ('subject_name', 'subject_translated')
    readonly_fields = ('created_at',)
    actions = ['approve_requests', 'approve_all_pending', 'reject_requests']

    def _do_approve(self, request, pending_queryset):
        from django.utils import timezone
        from django.db import connections
        import json
        conn = connections['honours']
        count = 0
        for pr in pending_queryset:
            cid = pr.country_id or 'BD'
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM cheradip_subject WHERE (country_id = %s OR country_id IS NULL) AND subject_tr = %s LIMIT 1",
                    [cid, pr.subject_translated]
                )
                existing = cur.fetchone()
            if not existing:
                subject_code = _generate_honours_subject_code(pr.subject_translated, cid)
                degree_type_val = (getattr(pr, 'degree_type', None) or '').strip()
                groups_json = json.dumps([degree_type_val]) if degree_type_val else None
                level_val = 'স্নাতক'
                level_tr_val = 'Honours'
                class_level_val = '13-16'
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO cheradip_subject (level, level_tr, groups, class_level, subject_name, subject_tr, subject_code, country_id, language_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)
                        """,
                        [level_val, level_tr_val, groups_json, class_level_val, pr.subject_name, pr.subject_translated, subject_code, cid]
                    )
            pr.status = PendingSubjectRequest.STATUS_APPROVED
            pr.reviewed_at = timezone.now()
            pr.reviewed_by = request.user
            pr.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
            pr.delete()
            count += 1
        return count

    @admin.action(description='Approve selected subject requests')
    def approve_requests(self, request, queryset):
        pending = queryset.filter(status=PendingSubjectRequest.STATUS_PENDING)
        count = self._do_approve(request, pending)
        self.message_user(request, f'Approved {count} subject request(s); added to honours DB and removed from list.')

    @admin.action(description='Approve all pending')
    def approve_all_pending(self, request, queryset):
        pending = PendingSubjectRequest.objects.filter(status=PendingSubjectRequest.STATUS_PENDING)
        count = self._do_approve(request, pending)
        self.message_user(request, f'Approved all {count} pending request(s); added to honours DB and removed from list.')

    @admin.action(description='Reject selected subject requests')
    def reject_requests(self, request, queryset):
        from django.utils import timezone
        pending = queryset.filter(status=PendingSubjectRequest.STATUS_PENDING)
        count = pending.update(
            status=PendingSubjectRequest.STATUS_REJECTED,
            reviewed_at=timezone.now(),
            reviewed_by=request.user
        )
        self.message_user(request, f'Rejected {count} subject request(s).')

@admin.register(Chapter)
class ChapterAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'subject_code', 'chapter_no', 'chapter_name', 'chapter_name_bn', 'created_at')
    search_fields = ('subject_code', 'chapter_no', 'chapter_name', 'chapter_name_bn')
    list_filter = ('subject_code', 'chapter_no', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Topic)
class TopicAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('id', 'chapter', 'topic_no', 'topic_name', 'topic_name_bn', 'created_at')
    search_fields = ('chapter__chapter_name', 'chapter__subject_code', 'topic_no', 'topic_name', 'topic_name_bn')
    list_filter = ('chapter', 'chapter__subject_code', 'topic_no', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


class InstituteNameByTypeFilter(admin.SimpleListFilter):
    title = 'Institute Name'
    parameter_name = 'institute_name'

    def lookups(self, request, model_admin):
        # Check if an institute type is selected in InstituteTypeFilter
        selected_type = request.GET.get('institute_type')
        
        if selected_type:
            # Fetch institute names for the selected institute type
            names = Institute.objects.filter(institute_type=selected_type).values_list('institute_name', flat=True).distinct()
            return [(name, name) for name in names]
        return []

    def queryset(self, request, queryset):
        if self.value():
            # Filter queryset by selected institute_name
            return queryset.filter(institutes__institute_name=self.value()).distinct()
        return queryset


class InstituteTypeFilter(admin.SimpleListFilter):
    title = 'Institute Type'
    parameter_name = 'institute_type'

    def lookups(self, request, model_admin):
        # Get distinct institute types
        types = Institute.objects.values_list('institute_type', flat=True).distinct()
        return [(institute_type, institute_type) for institute_type in types if institute_type]

    def queryset(self, request, queryset):
        if self.value():
            # Filter by the selected institute type
            return queryset.filter(institutes__institute_type=self.value()).distinct()
        return queryset


@admin.register(Mcq_ict)
class McqIctAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('qid', 'subject_code', 'chapter', 'topic', 'difficulty_level', 'is_active', 'answer', 'created_at')
    search_fields = (
        'qid', 'question', 'uddipok', 'answer', 'explanation',
        'subject_code', 'chapter__chapter_no', 'chapter__chapter_name',
        'topic__topic_no', 'topic__topic_name',
    )
    list_filter = ('subject_code', 'chapter', 'topic', 'difficulty_level', 'is_active', 'answer', InstituteTypeFilter, InstituteNameByTypeFilter, 'years', 'created_at')
    filter_horizontal = ('institutes', 'years')
    readonly_fields = ('qid', 'created_at', 'updated_at')
    fieldsets = (
        ('Question Information', {
            'fields': ('qid', 'subject_code', 'chapter', 'topic', 'question', 'uddipok', 'img_question', 'img_uddipok')
        }),
        ('Options', {
            'fields': ('option1', 'option2', 'option3', 'option4', 'answer')
        }),
        ('Additional Information', {
            'fields': ('explanation', 'img_explanation', 'difficulty_level', 'is_active')
        }),
        ('Relationships', {
            'fields': ('institutes', 'years')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Institute)
class InstituteAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('institute_code', 'institute_name', 'institute_name_bn', 'institute_type', 'created_at')
    search_fields = ('institute_code', 'institute_name', 'institute_name_bn', 'institute_type')
    list_filter = ('institute_type', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Year)
class YearAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('year_code', 'year_name', 'year_name_bn', 'start_year', 'end_year', 'created_at')
    search_fields = ('year_code', 'year_name', 'year_name_bn')
    list_filter = ('year_code', 'start_year', 'end_year', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Institutes)
class InstitutesAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('eiinNo', 'instituteName', 'instituteTypeName', 'districtName', 'isGovt')
    search_fields = ('eiinNo', 'instituteName', 'instituteNameBn', 'districtName', 'thanaName')
    list_filter = ('instituteTypeName', 'isGovt', 'divisionName', 'districtName')


# Unregister any model whose table does not exist in its routed database (all DBs)
def _unregister_models_with_missing_tables():
    from django.apps import apps
    from cheradip.model_table_check import get_models_with_missing_tables
    missing = get_models_with_missing_tables()
    for (app_label, model_name) in list(missing):
        try:
            model = apps.get_model(app_label, model_name)
            if model in admin.site._registry:
                admin.site.unregister(model)
        except Exception:
            pass


_unregister_models_with_missing_tables()