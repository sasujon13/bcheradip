from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Book, BookAsset, BookBuildJob, Brand, Cart, CartItem, Category, CommerceNotification, Coupon, ImportJob,
    InventoryMovement, Order, OrderItem, OrderStatusHistory, Payment, Product,
    ProductImage, ProductVariant, Review, Shipment, DeliverySettings,
)
from .book_catalog import sync_book_catalog
from .book_builder import build_book_asset
from .order_service import change_order, change_payment
from .admin_forms import OrderAdminForm, PaymentAdminForm, DeliverySettingsAdminForm, ShipmentAdminForm, ProductVariantAdminForm
from .pricing import calculate_price
from .delivery_rates import listing_defaults
from . import supplier_admin  # noqa: F401 - register private sourcing tools


for model in (
    Category, Brand, ProductImage,
    Cart, CartItem, Coupon,
    Review, CommerceNotification, ImportJob,
):
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass


class CatalogReviewFilter(admin.SimpleListFilter):
    title = 'Catalog review'
    parameter_name = 'catalog_review'
    def lookups(self, request, model_admin):
        return [('category', 'Category needs review'), ('variants', 'Size/options need verification'), ('conflicts', 'Specification conflicts')]
    def queryset(self, request, queryset):
        if self.value() == 'category': return queryset.filter(attributes___catalog__status='needs_review')
        if self.value() == 'variants': return queryset.filter(attributes___catalog__variant_review=True)
        if self.value() == 'conflicts': return queryset.exclude(attributes___catalog__conflicts={}).filter(attributes___catalog__conflicts__isnull=False)
        return queryset


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'is_sample', 'updated_at')
    search_fields = ('name', 'slug', 'variants__sku')
    list_filter = ('status', 'is_sample', CatalogReviewFilter)
    actions = ('confirm_category', 'recheck_options')

    @admin.action(description='Recheck size/option mappings after supplier verification', permissions=['change'])
    def recheck_options(self, request, queryset):
        from .product_content import source_for, variant_family, option_review
        from django.db import transaction
        for pk in queryset.values_list('pk', flat=True):
            with transaction.atomic(using='ecommerce'):
                row=Product.objects.using('ecommerce').select_for_update().get(pk=pk)
                source=source_for(row)
                review=bool(source and option_review(source,variant_family(row)))
                row.attributes={**row.attributes,'_catalog':{**row.attributes.get('_catalog',{}),'variant_review':review}}
                row.save(using='ecommerce',update_fields=['attributes','updated_at'])

    @admin.action(description='Confirm current categories and preserve these assignments', permissions=['change'])
    def confirm_category(self, request, queryset):
        from django.db import transaction
        for pk in queryset.values_list('pk', flat=True):
            with transaction.atomic(using='ecommerce'):
                row = Product.objects.using('ecommerce').select_for_update().get(pk=pk)
                from .catalog_structure import GENERIC, clean
                if not row.category.is_active or GENERIC.fullmatch(clean(row.category.name)): continue
                meta = row.attributes.get('_catalog', {})
                row.attributes = {**row.attributes, '_catalog': {**meta, 'manual_category': True, 'status': 'assigned'}}
                row.save(using='ecommerce', update_fields=['attributes','updated_at'])

    def get_deleted_objects(self, objs, request):
        from .models import OrderItem
        deleted, counts, permissions, protected = super().get_deleted_objects(objs, request)
        if OrderItem.objects.using('ecommerce').filter(product_id__in=[obj.pk for obj in objs]).exists():
            protected.append('Existing order history. Archive these products instead of deleting them.')
        return deleted, counts, permissions, protected

    def delete_queryset(self, request, queryset):
        from django.core.exceptions import PermissionDenied
        from .models import OrderItem
        with transaction.atomic(using='ecommerce'):
            ids = list(queryset.select_for_update().values_list('pk', flat=True))
            if OrderItem.objects.using('ecommerce').filter(product_id__in=ids).exists():
                raise PermissionDenied('Products with order history must be archived, not deleted.')
            queryset.delete()

    def delete_model(self, request, obj):
        self.delete_queryset(request, Product.objects.using('ecommerce').filter(pk=obj.pk))


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    form = ProductVariantAdminForm
    readonly_fields = ('pricing_summary',)

    @admin.display(description='Saved-cost price estimate')
    def pricing_summary(self, obj):
        if not obj or obj.cost_price is None:
            return 'Enter the source cost and calculator fields. Price changes only if the apply checkbox is selected.'
        try:
            result = calculate_price(obj.cost_price, obj.pricing_inputs or listing_defaults(DeliverySettings.current(),obj.weight_grams)[0], subsidy_enabled=DeliverySettings.current().delivery_subsidy_enabled,rules=DeliverySettings.current().pricing_rules)
        except ValueError as exc:
            return str(exc)
        return format_html('Costs: Tk {} · Delivery subsidy: Tk {} · Markup: {}% · Profit estimate: Tk {} · Suggested: Tk {}. Existing price is unchanged unless explicitly applied.',
            result['total_cost'], result['delivery_subsidy'], result['markup_percent'], result['profit_amount'], result['suggested_price'])


@admin.register(DeliverySettings)
class DeliverySettingsAdmin(admin.ModelAdmin):
    form = DeliverySettingsAdminForm
    fields = ('dhaka_charge', 'outside_dhaka_charge', 'cod_percent', 'delivery_subsidy_enabled', 'cost_defaults', 'pricing_rules', 'courier_profiles', 'unpaid_reservation_hours', 'support_phone', 'return_policy')

    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        if 'pricing_rules' in form.changed_data:
            from .supplier_service import audit
            audit('central_pricing_rules_saved',request.user.pk,rules=obj.pricing_rules,
                  existing_orders_unchanged=True,source='django_admin')

    def has_add_permission(self, request):
        return not DeliverySettings.objects.using('ecommerce').exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    form = ShipmentAdminForm
    list_display = ('order', 'carrier', 'tracking_number', 'status', 'delivered_at')

    def save_model(self, request, obj, form, change):
        from django.core.exceptions import PermissionDenied
        from .order_service import save_shipment
        if obj.status != 'preparing' and (not change or 'status' in form.changed_data) and not request.user.has_perm('ecommerce.change_order'):
            raise PermissionDenied('Permission to change orders is required for fulfilment updates.')
        saved = save_shipment(obj if change else None,
            {field: getattr(obj, field) for field in ('order', 'carrier', 'tracking_number', 'tracking_url', 'status', 'shipped_at', 'delivered_at')}, request.user.pk)
        obj.pk = saved.pk


class ImmutableCommerceRecordAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for immutable_model in (InventoryMovement, OrderItem, OrderStatusHistory):
    admin.site.register(immutable_model, ImmutableCommerceRecordAdmin)


@admin.action(description='Mark selected orders as Order Completed')
def complete_orders(modeladmin, request, queryset):
    completed = 0
    for order in queryset.exclude(status='completed'):
        try:
            change_order(order.pk, 'completed', request.user.pk, 'Order completed manually by administration.')
            completed += 1
        except ValueError as exc:
            modeladmin.message_user(request, f'{order.number}: {exc}', level='error')
    modeladmin.message_user(request, f'{completed} order(s) marked as completed.')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = (
        'number', 'customer_name', 'grand_total', 'payment_status', 'status',
        'created_at', 'fulfilled_at',
    )
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('number', 'customer_name', 'email', 'phone')
    readonly_fields = ('number', 'tracking_token', 'checkout_token', 'payment_status', 'created_at', 'updated_at')
    actions = (complete_orders,)

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields if field.name not in {'status', 'admin_note'})

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # Route the form through the very same state machine as the API.
        change_order(obj.pk, obj.status, request.user.pk, 'Updated by administration.', obj.admin_note)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    form = PaymentAdminForm
    list_display = ('order', 'method', 'amount', 'status', 'created_at')
    readonly_fields = ('order', 'method', 'amount', 'transaction_id', 'proof_url', 'payer_phone', 'confirmed_by', 'confirmed_at', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        change_payment(obj.pk, obj.status, request.user.pk, obj.note)


class BookAssetInline(admin.TabularInline):
    model = BookAsset
    extra = 1
    fields = ('title', 'asset_type', 'file_format', 'file', 'external_url', 'is_primary', 'is_downloadable', 'sort_order')


class BookBuildJobInline(admin.TabularInline):
    model = BookBuildJob
    extra = 0
    fields = ('status', 'output_format', 'progress', 'message', 'result_asset', 'created_by')
    readonly_fields = ('created_by',)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'book_type', 'audience', 'source_type', 'digital_price', 'hard_copy_available', 'hard_copy_quantity', 'status', 'featured', 'updated_at')
    list_filter = ('status', 'book_type', 'audience', 'source_type', 'language', 'hard_copy_available', 'featured')
    search_fields = ('title', 'title_bn', 'author', 'publisher', 'isbn', 'tags')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('product', 'created_at', 'updated_at')
    inlines = (BookAssetInline, BookBuildJobInline)
    actions = ('build_pdf', 'build_docx', 'build_html', 'build_epub')
    fieldsets = (
        ('Book identity', {'fields': ('title', 'title_bn', 'slug', 'subtitle', 'description', 'book_type', 'audience', 'status', 'featured')}),
        ('Author and publication', {'fields': ('author', 'editor', 'publisher', 'isbn', 'language', 'edition', 'publication_year', 'page_count', 'tags')}),
        ('Create from questions or upload', {'fields': ('source_type', 'source_config', 'preview_text')}),
        ('Smart cover and media', {'fields': ('cover_image', 'wide_cover_image', 'cover_design', 'video_url')}),
        ('Sales and inventory', {'fields': ('digital_price', 'compare_at_price', 'hard_copy_available', 'hard_copy_price', 'hard_copy_quantity', 'weight_grams')}),
        ('Linked catalog record', {'fields': ('product', 'created_by', 'created_at', 'updated_at')}),
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user.pk
        super().save_model(request, obj, form, change)
        sync_book_catalog(obj)

    def _build_selected(self, request, queryset, output_format):
        completed = 0
        failed = []
        for book in queryset:
            job = BookBuildJob.objects.using('ecommerce').create(
                book=book, output_format=output_format, source_config=book.source_config,
                created_by=request.user.pk,
            )
            try:
                build_book_asset(job)
                completed += 1
            except Exception as exc:
                failed.append(f'{book.title}: {exc}')
        if completed:
            self.message_user(request, f'Created {completed} {output_format.upper()} book file(s).')
        if failed:
            self.message_user(request, 'Failed: ' + '; '.join(failed[:5]), level='error')

    @admin.action(description='Build selected books as PDF')
    def build_pdf(self, request, queryset):
        self._build_selected(request, queryset, 'pdf')

    @admin.action(description='Build selected books as editable DOCX')
    def build_docx(self, request, queryset):
        self._build_selected(request, queryset, 'docx')

    @admin.action(description='Build selected books as HTML')
    def build_html(self, request, queryset):
        self._build_selected(request, queryset, 'html')

    @admin.action(description='Build selected books as EPUB')
    def build_epub(self, request, queryset):
        self._build_selected(request, queryset, 'epub')


@admin.register(BookAsset)
class BookAssetAdmin(admin.ModelAdmin):
    list_display = ('title', 'book', 'asset_type', 'file_format', 'file_size', 'is_primary', 'is_downloadable', 'updated_at')
    list_filter = ('asset_type', 'file_format', 'is_primary', 'is_downloadable')
    search_fields = ('title', 'book__title', 'external_url')


@admin.register(BookBuildJob)
class BookBuildJobAdmin(admin.ModelAdmin):
    list_display = ('book', 'output_format', 'status', 'progress', 'created_by', 'created_at')
    list_filter = ('status', 'output_format')
    search_fields = ('book__title', 'message')

