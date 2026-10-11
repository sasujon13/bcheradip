from django.contrib import admin
from django.utils import timezone

from .models import (
    Book, BookAsset, BookBuildJob, Brand, Cart, CartItem, Category, CommerceNotification, Coupon, ImportJob,
    InventoryMovement, Order, OrderItem, OrderStatusHistory, Payment, Product,
    ProductImage, ProductVariant, Review, Shipment,
)
from .book_catalog import sync_book_catalog
from .book_builder import build_book_asset


for model in (
    Category, Brand, Product, ProductVariant, ProductImage, InventoryMovement,
    Cart, CartItem, Coupon, OrderItem, Payment, Shipment,
    OrderStatusHistory, Review, CommerceNotification, ImportJob,
):
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass


@admin.action(description='Mark selected orders as Order Completed')
def complete_orders(modeladmin, request, queryset):
    completed = 0
    for order in queryset.exclude(status='completed'):
        order.status = 'completed'
        order.payment_status = 'paid'
        order.fulfilled_at = order.fulfilled_at or timezone.now()
        order.save(using='ecommerce', update_fields=['status', 'payment_status', 'fulfilled_at', 'updated_at'])
        OrderStatusHistory.objects.using('ecommerce').create(
            order=order,
            status='completed',
            note='Order completed manually by administration.',
            actor_id=request.user.pk,
        )
        CommerceNotification.objects.using('ecommerce').create(
            kind='order',
            title=f'Order {order.number}: completed',
            message='Your order has been completed.',
            link=f'/history?order={order.number}',
            customer_id=order.customer_id,
        )
        completed += 1
    modeladmin.message_user(request, f'{completed} order(s) marked as completed.')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'number', 'customer_name', 'grand_total', 'payment_status', 'status',
        'created_at', 'fulfilled_at',
    )
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('number', 'customer_name', 'email', 'phone')
    readonly_fields = ('number', 'tracking_token', 'created_at', 'updated_at')
    actions = (complete_orders,)


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

