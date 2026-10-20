"""
Admin for cheradip default-DB models only.
Tables: Country, Location, Item, Transaction, OrderDetail, Customer, CustomerToken, Notification, JsonData.
"""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from django.db import transaction
from django.utils import timezone
from django.shortcuts import render, redirect
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator
from django.urls import path, reverse
from django.contrib.admin.views.decorators import staff_member_required
from .admin_access import CustomerCreationForm, CustomerChangeForm, CustomerPasswordChangeForm, settings_revision
from .models import (
    Country,
    Location,
    Item,
    Transaction,
    OrderDetail,
    Customer,
    CustomerToken,
    Notification,
    JsonData,
    LiveClass,
    TrxManagement,
    PackagePlan,
    PackageSubscription,
    MembershipProgress,
    ReferralCommission,
    RewardsWallet,
    WithdrawalRequest,
    InstituteSourceSnapshot,
    InstituteTeacher,
    InstituteUpdateRun,
    InstituteUpdateAttempt,
    InstituteRefreshRequest,
    InstituteRefreshEvent,
    InstituteScrapePage,
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
        # Customer uploads must not let ordinary staff import is_superuser,
        # is_staff, settings or password values through the generic importer.
        if model is Customer and not request.user.is_superuser:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('Only an administrator can import customer accounts.')
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
class CustomerAdmin(BulkImportCsvJsonMixin, UserAdmin):
    form = CustomerChangeForm
    add_form = CustomerCreationForm
    change_password_form = CustomerPasswordChangeForm
    change_list_template = 'admin/cheradip/customer/change_list.html'
    change_form_template = 'admin/cheradip/customer/change_form.html'
    ordering = ('-date_joined',)
    list_display = ('username', 'fullName', 'account_role', 'acctype', 'email', 'is_active', 'is_staff', 'is_superuser', 'permission_link', 'date_joined')
    search_fields = ('username', 'fullName', 'email', 'division', 'district')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'acctype', 'group', 'gender', 'date_joined')
    readonly_fields = ('account_role', 'date_joined', 'last_login', 'updated_at')
    filter_horizontal = ('groups', 'user_permissions')
    autocomplete_fields = ('referred_by',)
    add_fieldsets = (
        ('Create user / customer', {'classes': ('wide',), 'fields': (
            'username', 'fullName', 'acctype', 'email', 'usable_password', 'password1', 'password2',
        )}),
        ('Administration & marketplace access', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    fieldsets = (
        ('Account', {'fields': ('username', 'fullName', 'acctype', 'email', 'profile_image')}),
        ('Administration & marketplace access', {
            'description': 'Customers and administrators use the same Customer account. An existing administrator can grant Staff access for the backend and marketplace Manage menu. Grant specific eCommerce permissions below, or select Administrator for full access. Staff cannot grant themselves or others administrator access. Sign in to the website with this same account; website and Django logins on different hosts do not share a browser session.',
            'fields': ('account_role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Education & personal details', {'classes': ('collapse',), 'fields': (
            'group', 'gender', 'country_code', 'date_of_birth', 'class_name', 'department',
            'teacher_level', 'teacher_subject_code', 'teacher_department_code', 'teacher_department_name',
        )}),
        ('Address & contact', {'classes': ('collapse',), 'fields': (
            'division', 'district', 'thana', 'union', 'village', 'phone_alternate',
        )}),
        ('Account settings & security', {'classes': ('collapse',), 'fields': (
            'password', 'whatsapp_apikey', 'settings_editor', 'referred_by', 'date_joined', 'last_login', 'updated_at',
        )}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).defer('settings')

    def get_urls(self):
        return [path('<path:object_id>/settings-json/', self.admin_site.admin_view(self.settings_json),
                     name='cheradip_customer_settings_json'), *super().get_urls()]

    @method_decorator(require_GET)
    def settings_json(self, request, object_id):
        if not request.user.is_superuser:
            raise PermissionDenied('Settings are administrator-managed.')
        obj = self.get_object(request, object_id)
        if obj is None:
            raise Http404
        if not self.has_view_permission(request, obj):
            raise PermissionDenied
        value = obj.settings
        response = JsonResponse({'settings': value, 'revision': settings_revision(value)})
        response['Cache-Control'] = 'no-store, private'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    @admin.display(description='Settings')
    def settings_editor(self, obj):
        return 'Settings are administrator-managed and load only when opened by an administrator.'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'referred_by':
            kwargs['queryset'] = Customer.objects.defer('settings')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='Access role')
    def account_role(self, obj):
        return 'Administrator' if obj.is_superuser else 'Staff' if obj.is_staff else 'Customer'

    @admin.display(description='Permissions')
    def permission_link(self, obj):
        return format_html('<a href="{}">Permissions</a>', reverse('admin:cheradip_customer_change', args=[obj.pk]))

    @admin.display(description='Password')
    def password_status(self, obj):
        return 'Password is set (administrator-managed)' if obj and obj.has_usable_password() else 'Password sign-in disabled'

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser or obj is None:
            return fieldsets
        return tuple((title, {**options, 'fields': tuple('password_status' if field == 'password' else field for field in options['fields'])})
                     for title, options in fieldsets)

    def has_change_permission(self, request, obj=None):
        if obj and (obj.is_staff or obj.is_superuser) and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and (obj.is_staff or obj.is_superuser) and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if not request.user.is_superuser and queryset.filter(is_staff=True).exists():
            raise PermissionDenied('Only an administrator can delete staff accounts.')
        if not request.user.is_superuser and queryset.filter(is_superuser=True).exists():
            raise PermissionDenied('Only an administrator can delete administrator accounts.')
        super().delete_queryset(request, queryset)

    def user_change_password(self, request, id, form_url=''):
        if not request.user.is_superuser:
            raise PermissionDenied('Only an administrator can reset account passwords here.')
        return super().user_change_password(request, id, form_url)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and 'settings_editor' in form.base_fields:
            form.base_fields['settings_editor'].widget.attrs['data-settings-url'] = reverse(
                'admin:cheradip_customer_settings_json', args=[obj.pk])
        labels = {
            'is_staff': ('Staff access', 'Allows this account to sign in to Django administration and see Manage in the marketplace. Specific model permissions are still required.'),
            'is_superuser': ('Administrator — full access', 'Grants every permission, including assigning administrator access to other users. Select only for a trusted site administrator. Staff access is enabled automatically.'),
            'groups': ('Permission groups', 'Assign existing groups for shared staff permissions. This is separate from the education group (Science, Business Studies, Humanities).'),
            'user_permissions': ('Individual permissions', 'For marketplace product management select the required eCommerce product, variant, image, category and brand permissions. Orders, payments and other tools have separate permissions.'),
        }
        for name, (label, help_text) in labels.items():
            if name in form.base_fields:
                form.base_fields[name].label = label
                form.base_fields[name].help_text = help_text
        return form

    def save_model(self, request, obj, form, change):
        if request.user.is_superuser and getattr(form, 'settings_changed', False):
            obj.settings = form.cleaned_data['settings_editor']
        if request.user.is_superuser and obj.is_superuser:
            obj.is_staff = True
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if request.user.is_superuser:
            return fields
        return (*fields, 'settings', 'settings_editor', 'password', 'password_status', 'is_staff', 'is_superuser', 'groups', 'user_permissions')


@admin.register(LiveClass)
class LiveClassAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'teacher_name', 'bangladesh_start', 'status', 'is_published')
    list_filter = ('status', 'is_published', 'level')
    search_fields = ('title', 'subject', 'topic', 'teacher_name')
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    fieldsets = (
        ('Class details', {'fields': ('title', 'subject', 'level', 'topic', 'teacher_name', 'description')}),
        ('Schedule & joining', {'description': 'All class times are Bangladesh time (Asia/Dhaka). Published upcoming classes appear in Live Class and dashboard Quick Actions.',
                                'fields': ('starts_at', 'ends_at', 'join_url', 'status', 'is_published')}),
        ('Audit', {'classes': ('collapse',), 'fields': ('created_by', 'created_at', 'updated_at')}),
    )

    @admin.display(description='Start (Bangladesh time)', ordering='starts_at')
    def bangladesh_start(self, obj):
        from zoneinfo import ZoneInfo
        return timezone.localtime(obj.starts_at, ZoneInfo('Asia/Dhaka')).strftime('%d-%b %I:%M %p')

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        with timezone.override('Asia/Dhaka'):
            response = super().changeform_view(request, object_id, form_url, extra_context)
            if hasattr(response, 'render'):
                response.render()
            return response

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CustomerToken)
class CustomerTokenAdmin(BulkImportCsvJsonMixin, admin.ModelAdmin):
    list_display = ('key', 'customer', 'created', 'expires_at')
    search_fields = ('key', 'customer__username', 'customer__fullName')
    list_filter = ('created', 'expires_at')
    readonly_fields = ('key', 'created')


@admin.register(PackagePlan)
class PackagePlanAdmin(admin.ModelAdmin):
    list_display = ('code', 'audience', 'name', 'track', 'duration_months', 'price', 'list_price', 'is_active', 'sort_order')
    list_filter = ('audience', 'track', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('sort_order', 'track')


@admin.action(description='Activate selected plans using normal wallet/payment rules')
def activate_subscriptions(modeladmin, request, queryset):
    from .package_service import activate_plan
    activated = 0
    for subscription in queryset.select_related('plan', 'customer'):
        try:
            _, _, created, message = activate_plan(subscription.customer, subscription.plan, subscription.payment_reference)
            activated += int(created)
            modeladmin.message_user(request, message)
        except ValueError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
    modeladmin.message_user(request, f'{activated} subscription(s) activated.')


@admin.register(PackageSubscription)
class PackageSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'plan', 'order_status', 'status', 'payable_amount', 'badge_discount_percent', 'payment_reference', 'starts_at', 'ends_at')
    list_filter = ('order_status', 'status', 'plan__audience', 'plan__track', 'created_at')
    search_fields = ('order_number', 'customer__username', 'customer__fullName', 'plan__code', 'payment_reference')
    actions = (activate_subscriptions,)
    readonly_fields = ('order_number', 'plan_price', 'badge_discount_percent', 'payable_amount', 'created_at', 'updated_at')

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MembershipProgress)
class MembershipProgressAdmin(admin.ModelAdmin):
    list_display = ('customer', 'audience', 'account_type', 'badge', 'metric_count', 'recent_metric_count', 'passing_rate', 'discount_percent', 'maintenance_met', 'evaluated_at')
    list_filter = ('audience', 'account_type', 'badge', 'maintenance_met')
    search_fields = ('customer__username', 'customer__fullName')
    readonly_fields = ('evaluated_at',)

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReferralCommission)
class ReferralCommissionAdmin(admin.ModelAdmin):
    list_display = ('referrer', 'referred_customer', 'subscription', 'gross_amount', 'reference_value_percent', 'commission_coins', 'created_at')
    search_fields = ('referrer__username', 'referred_customer__username')
    readonly_fields = ('created_at',)

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RewardsWallet)
class RewardsWalletAdmin(admin.ModelAdmin):
    list_display = ('customer', 'available_taka', 'lifetime_earned_taka', 'lifetime_withdrawn_taka', 'updated_at')
    search_fields = ('customer__username', 'customer__fullName')
    readonly_fields = ('customer', 'available_taka', 'lifetime_earned_taka', 'lifetime_withdrawn_taka', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.action(description='Mark selected withdrawals as processing before sending payment')
def process_withdrawals(modeladmin, request, queryset):
    processing = queryset.filter(status='pending').update(status='processing')
    modeladmin.message_user(
        request,
        f'{processing} withdrawal request(s) marked processing. Send payment, then approve.',
    )


@admin.action(description='Mark selected processing withdrawals paid and approved')
def approve_withdrawals(modeladmin, request, queryset):
    approved = 0
    with transaction.atomic():
        rows = WithdrawalRequest.objects.select_for_update().filter(pk__in=queryset.values('pk'))
        for row in rows.select_related('customer'):
            if row.status != 'processing':
                continue
            if not row.reserved_coins:
                modeladmin.message_user(request, f'Withdrawal {row.pk} predates wallet reservation. Reconcile it manually before approval.', level=messages.WARNING)
                continue
            wallet, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=row.customer)
            wallet.lifetime_withdrawn_taka += row.amount_taka
            wallet.save(update_fields=['lifetime_withdrawn_taka', 'updated_at'])
            row.status = 'approved'
            row.processed_at = timezone.now()
            row.processed_by = request.user
            row.save(update_fields=['status', 'processed_at', 'processed_by'])
            approved += 1
    modeladmin.message_user(request, f'{approved} withdrawal request(s) marked paid and approved.')


@admin.action(description='Reject selected withdrawals and refund rewards balance')
def reject_withdrawals(modeladmin, request, queryset):
    rejected = 0
    with transaction.atomic():
        rows = WithdrawalRequest.objects.select_for_update().filter(pk__in=queryset.values('pk'))
        for row in rows.select_related('customer'):
            if row.status not in {'pending', 'processing'}:
                continue
            customer = Customer.objects.select_for_update().get(pk=row.customer_id)
            wallet, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=row.customer)
            wallet.available_taka += row.amount_taka
            wallet.save(update_fields=['available_taka', 'updated_at'])
            if row.reserved_coins:
                from .wallet_service import wallet_coins
                customer.settings = {**(customer.settings or {}), 'balance': wallet_coins(customer) + row.reserved_coins}
                customer.save(update_fields=['settings'])
            row.status = 'rejected'
            row.processed_at = timezone.now()
            row.processed_by = request.user
            row.save(update_fields=['status', 'processed_at', 'processed_by'])
            rejected += 1
    modeladmin.message_user(request, f'{rejected} withdrawal request(s) rejected and refunded.')


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'method', 'account_number', 'amount_taka', 'status', 'requested_at', 'processed_at')
    list_filter = ('status', 'method', 'requested_at')
    search_fields = ('customer__username', 'customer__fullName', 'account_number', 'account_name')
    readonly_fields = (
        'customer', 'method', 'account_name', 'account_number', 'amount_taka',
        'balance_before_taka', 'balance_after_taka', 'status', 'requested_at',
        'processed_at', 'processed_by',
    )
    actions = (process_withdrawals, approve_withdrawals, reject_withdrawals)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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


@admin.register(TrxManagement)
class TrxManagementAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'trxid',
        'media',
        'received_amount',
        'currency',
        'sender_contact',
        'transaction_date',
        'transaction_time',
        'confidence',
        'verified',
        'status',
        'token',
    )
    search_fields = ('trxid', 'sender_contact', 'media')
    list_filter = ('media', 'currency', 'status', 'verified')


@admin.register(InstituteSourceSnapshot)
class InstituteSourceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('eiin', 'last_banbeis_sync_at', 'last_emis_sync_at')
    search_fields = ('eiin',)
    readonly_fields = ('eiin', 'banbeis', 'emis', 'last_banbeis_sync_at', 'last_emis_sync_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstituteTeacher)
class InstituteTeacherAdmin(admin.ModelAdmin):
    list_display = ('eiin', 'name', 'name_bn', 'designation', 'subject', 'joining_date', 'listed', 'last_seen_at')
    list_filter = ('listed', 'last_seen_at')
    search_fields = ('eiin', 'name', 'name_bn', 'subject')
    readonly_fields = ('eiin', 'source_row_id', 'name', 'name_bn', 'designation', 'subject',
                       'pds_id', 'index_no', 'district_name', 'bcs_batch',
                       'joining_date', 'present_joining_date', 'photo_url', 'mobile', 'email',
                       'position', 'listed', 'last_seen_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstituteUpdateRun)
class InstituteUpdateRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'total', 'cursor', 'started_at', 'completed_at')
    readonly_fields = ('id', 'status', 'total', 'cursor', 'locked_until', 'started_at', 'completed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstituteUpdateAttempt)
class InstituteUpdateAttemptAdmin(admin.ModelAdmin):
    list_display = ('eiin', 'run', 'status', 'outcome', 'attempts', 'updated_at')
    list_filter = ('status', 'outcome', 'updated_at')
    search_fields = ('eiin', 'detail')
    readonly_fields = ('run', 'eiin', 'status', 'outcome', 'detail', 'attempts', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstituteRefreshRequest)
class InstituteRefreshRequestAdmin(admin.ModelAdmin):
    list_display = ('eiin', 'status', 'outcome', 'requested_at', 'completed_at')
    list_filter = ('status', 'completed_at')
    search_fields = ('eiin',)
    readonly_fields = ('eiin', 'status', 'requested_at', 'started_at', 'completed_at',
                       'locked_until', 'outcome', 'detail')

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstituteRefreshEvent)
class InstituteRefreshEventAdmin(admin.ModelAdmin):
    list_display = ('eiin', 'status', 'outcome', 'checked_at')
    list_filter = ('status', 'outcome', 'checked_at')
    search_fields = ('eiin', 'detail')
    readonly_fields = ('eiin', 'status', 'outcome', 'detail', 'checked_at')

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InstituteScrapePage)
class InstituteScrapePageAdmin(admin.ModelAdmin):
    list_display = ('page', 'size', 'created', 'updated', 'unchanged', 'failed', 'processed_by', 'processed_at')
    list_filter = ('size', 'processed_at')
    readonly_fields = ('page', 'size', 'source', 'created', 'updated', 'unchanged', 'failed', 'source_total', 'processed_by', 'processed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False


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
