from rest_framework import serializers

from .models import (
    Book, BookAsset, BookBuildJob, Brand, Cart, CartItem, Category, CommerceNotification, InventoryMovement,
    Order, OrderItem, OrderStatusHistory, Payment, Product, ProductImage,
    ProductVariant, Review, Shipment,
)
from .book_catalog import book_variant_ids
from .pricing import normalize_costs


def public_product_images(product):
    """Never let a historical logo/related-product image outrank verified source media."""
    from .models import SupplierOffer
    source = SupplierOffer.objects.using('ecommerce').filter(imported_product_id=product.pk).values_list('source_product_id', 'source_product__last_run_id').first()
    images = product.images.all()
    if source and source[0]:
        from .supplier_media import source_image_url_condition
        images = images.filter(source_media__product_id=source[0], source_media__last_run_id=source[1],
            source_media__metadata__verified_image=True).filter(source_image_url_condition())
    return images


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'parent_id', 'description', 'image_url', 'sort_order', 'is_active', 'product_count')


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ('id', 'url', 'alt_text', 'position', 'variant_id')


class ProductVariantSerializer(serializers.ModelSerializer):
    def validate_pricing_inputs(self, value):
        try:
            return {} if value == {} else normalize_costs(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    class Meta:
        model = ProductVariant
        fields = '__all__'
        read_only_fields = ('product', 'created_at', 'updated_at')


class ProductListSerializer(serializers.ModelSerializer):
    stock_confirmation_required = serializers.SerializerMethodField()
    quantity_unspecified = serializers.BooleanField(source='attributes._stock_confirmation_required',read_only=True,default=False)
    def get_stock_confirmation_required(self,obj):return False
    discount_percent = serializers.SerializerMethodField()

    def get_discount_percent(self,obj):
        from decimal import Decimal
        return int((obj.compare_at_price-obj.price)*100/obj.compare_at_price) if obj.price is not None and obj.compare_at_price and obj.compare_at_price>obj.price else 0
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    compare_at_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, allow_null=True)
    stock = serializers.IntegerField(read_only=True)
    image_url = serializers.CharField(read_only=True)
    default_variant_id = serializers.IntegerField(read_only=True)
    allow_backorder = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'short_description', 'category_id', 'category_name',
            'brand_id', 'brand_name', 'status', 'featured', 'tags', 'price',
            'compare_at_price', 'stock', 'image_url', 'is_sample', 'source_url',
            'default_variant_id', 'allow_backorder', 'stock_confirmation_required','quantity_unspecified','discount_percent',
        )


class ProductDetailSerializer(serializers.ModelSerializer):
    supplier_reference = serializers.SerializerMethodField()

    def get_supplier_reference(self, obj):
        from .models import SupplierOffer
        return SupplierOffer.objects.using('ecommerce').filter(imported_product=obj).values_list('url', flat=True).first() or ''

    def validate_supplier_delivery_rates(self, value):
        from .supplier_delivery import validate_rates
        try:
            return validate_rates(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate(self, data):
        from .supplier_guards import check_publication
        if self.instance:
            try:
                check_publication(self.instance, data.get('status', self.instance.status))
            except ValueError as exc:
                raise serializers.ValidationError({'status': str(exc)})
        return data

    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    approved_reviews = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = '__all__'

    def get_approved_reviews(self, obj):
        return ReviewSerializer(obj.reviews.filter(is_approved=True), many=True).data


class StorefrontVariantSerializer(serializers.ModelSerializer):
    stock_confirmation_required = serializers.SerializerMethodField()
    quantity_unspecified = serializers.SerializerMethodField()
    def get_quantity_unspecified(self,obj):
        from .supplier_confirmation import quantity_unspecified
        return quantity_unspecified(obj)
    discount_percent = serializers.SerializerMethodField()

    def get_stock_confirmation_required(self,obj):
        from .supplier_confirmation import required
        return required(obj)

    def get_discount_percent(self,obj):
        return int((obj.compare_at_price-obj.price)*100/obj.compare_at_price) if obj.compare_at_price and obj.compare_at_price>obj.price else 0
    class Meta:
        model = ProductVariant
        fields = ('id', 'title', 'sku', 'price', 'compare_at_price', 'stock', 'is_active',
                  'option1_name', 'option1_value', 'option2_name', 'option2_value',
                  'option3_name', 'option3_value', 'requires_shipping', 'allow_backorder','stock_confirmation_required','quantity_unspecified','discount_percent')


class StorefrontProductSerializer(ProductDetailSerializer):
    stock_confirmation_required = serializers.SerializerMethodField()
    quantity_unspecified = serializers.BooleanField(source='attributes._stock_confirmation_required',read_only=True,default=False)
    def get_stock_confirmation_required(self,obj):return False
    attributes = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    fulfilment_mode = serializers.SerializerMethodField()

    def get_attributes(self, obj):
        return {k: v for k, v in (obj.attributes or {}).items()
                if not k.startswith('_') and k not in
                ('manual_supplier_catalogue', 'supplier_publication_ready', 'source_stock_hold')}

    def get_fulfilment_mode(self,obj):
        from .manual_catalogue import is_manual
        if is_manual(obj): return 'manual_supplier_catalogue'
        from .models import SupplierOffer
        return 'staff_confirmed_supplier_pilot' if SupplierOffer.objects.using('ecommerce').filter(imported_product_id=obj.pk).exists() else 'standard'

    class Meta:
        model = Product
        fields = ('id', 'name', 'slug', 'description', 'short_description', 'category_name',
                  'brand_name', 'variants', 'images', 'approved_reviews', 'attributes', 'tags',
                  'delivery_dhaka_charge', 'delivery_outside_dhaka_charge', 'cod_percent', 'fulfilment_mode','stock_confirmation_required','quantity_unspecified')

    def get_variants(self, obj):
        return StorefrontVariantSerializer(obj.variants.filter(is_active=True), many=True).data

    def get_images(self, obj):
        return ProductImageSerializer(public_product_images(obj), many=True).data

    def get_approved_reviews(self, obj):
        return [{'id': row.pk, 'customer_name': row.customer_name, 'rating': row.rating,
                 'title': row.title, 'body': row.body, 'created_at': row.created_at}
                for row in obj.reviews.filter(is_approved=True)]


class BookAssetSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BookAsset
        fields = '__all__'
        read_only_fields = ('file_size', 'created_at', 'updated_at')

    def get_file_url(self, obj):
        if obj.asset_type == 'ebook':
            return ''
        if not obj.file:
            return obj.external_url
        request = self.context.get('request')
        url = f'/api/ecommerce/book-assets/{obj.pk}/download/'
        return request.build_absolute_uri(url) if request else url

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['file'] = self.get_file_url(instance)
        if instance.asset_type == 'ebook':
            data['external_url'] = ''
        return data


class BookSerializer(serializers.ModelSerializer):
    assets = serializers.SerializerMethodField()
    available_formats = serializers.SerializerMethodField()
    book_type_label = serializers.CharField(source='get_book_type_display', read_only=True)
    audience_label = serializers.CharField(source='get_audience_display', read_only=True)
    source_type_label = serializers.CharField(source='get_source_type_display', read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    wide_cover_image_url = serializers.SerializerMethodField()
    digital_variant_id = serializers.SerializerMethodField()
    hard_copy_variant_id = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = '__all__'
        read_only_fields = ('product', 'created_by', 'created_at', 'updated_at')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if hasattr(instance, 'storefront_hard_copy_stock'):
            data['hard_copy_quantity'] = instance.storefront_hard_copy_stock or 0
        elif instance.product_id:
            stock = ProductVariant.objects.using('ecommerce').filter(product_id=instance.product_id, sku__endswith='-HARDCOPY').values_list('stock', flat=True).first()
            data['hard_copy_quantity'] = stock or 0
        return data

    def _file_url(self, field):
        if not field:
            return ''
        # Uploaded public media is exposed by the existing /manage/media/ route.
        # A relative URL remains valid through the Angular proxy and production host.
        return field.url.replace('/media/', '/manage/media/', 1)

    def get_cover_image_url(self, obj):
        return self._file_url(obj.cover_image)

    def get_wide_cover_image_url(self, obj):
        return self._file_url(obj.wide_cover_image)

    def get_digital_variant_id(self, obj):
        if hasattr(obj, 'storefront_digital_variant_id'):
            return obj.storefront_digital_variant_id
        return book_variant_ids(obj)['digital_variant_id']

    def get_hard_copy_variant_id(self, obj):
        if hasattr(obj, 'storefront_hard_copy_variant_id'):
            return obj.storefront_hard_copy_variant_id
        return book_variant_ids(obj)['hard_copy_variant_id']

    def get_assets(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        is_admin = user and user.is_authenticated and (user.is_staff or user.is_superuser)
        if not is_admin and hasattr(obj, 'storefront_public_assets'):
            assets = obj.storefront_public_assets
        else:
            assets = obj.assets.all()
            if not is_admin:
                assets = assets.filter(asset_type__in=('sample', 'video'))
        return BookAssetSerializer(assets, many=True, context=self.context).data

    def get_available_formats(self, obj):
        if hasattr(obj, 'storefront_ebook_assets'):
            return list(dict.fromkeys(asset.file_format for asset in obj.storefront_ebook_assets))
        return list(obj.assets.filter(asset_type='ebook').values_list('file_format', flat=True).distinct())


class BookBuildJobSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)

    class Meta:
        model = BookBuildJob
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')


class CartItemSerializer(serializers.ModelSerializer):
    stock_confirmation_required = serializers.SerializerMethodField()
    quantity_unspecified = serializers.SerializerMethodField()

    def get_quantity_unspecified(self,obj):
        from .supplier_confirmation import quantity_unspecified
        return quantity_unspecified(obj.variant)

    def get_stock_confirmation_required(self,obj):
        from .supplier_confirmation import required
        return required(obj.variant)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    variant_title = serializers.CharField(source='variant.title', read_only=True)
    sku = serializers.CharField(source='variant.sku', read_only=True)
    unit_price = serializers.DecimalField(source='variant.price', max_digits=14, decimal_places=2, read_only=True)
    image_url = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ('id', 'variant_id', 'quantity', 'product_name', 'variant_title', 'sku', 'unit_price', 'image_url', 'line_total','stock_confirmation_required','quantity_unspecified')

    def get_image_url(self, obj):
        from django.db.models import Q
        images = public_product_images(obj.variant.product).filter(Q(variant_id=None)|Q(variant_id=obj.variant_id))
        image = images.filter(variant_id=obj.variant_id).first() or images.first()
        return image.url if image else ''

    def get_line_total(self, obj):
        return obj.variant.price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ('token', 'customer_id', 'email', 'checked_out', 'items', 'subtotal', 'created_at', 'updated_at')

    def get_subtotal(self, obj):
        return sum((item.variant.price * item.quantity for item in obj.items.select_related('variant')), 0)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = '__all__'


class AdminOrderItemSerializer(OrderItemSerializer):
    supplier_reference = serializers.SerializerMethodField()

    def get_supplier_reference(self, obj):
        from .models import SupplierOffer
        return SupplierOffer.objects.using('ecommerce').filter(imported_product_id=obj.product_id).values_list('url', flat=True).first() or ''


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('status', 'confirmed_by', 'confirmed_at', 'created_at', 'updated_at')


class CustomerPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ('id', 'method', 'amount', 'transaction_id', 'status', 'created_at')


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = '__all__'


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    def to_representation(self,instance):
        data=super().to_representation(instance)
        from .phone_display import local_contact
        if 'phone' in data:data['phone']=local_contact(data['phone'],(instance.shipping_address or {}).get('country_code','BD'))
        return data
    stock_confirmation_pending = serializers.SerializerMethodField()

    def get_stock_confirmation_pending(self,obj):
        from .supplier_confirmation import pending
        return pending(obj)
    items = AdminOrderItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    shipments = ShipmentSerializer(many=True, read_only=True)
    history = OrderStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = '__all__'


class CustomerOrderSerializer(OrderSerializer):
    """Never disclose internal notes, actor IDs or checkout credentials to customers."""
    payments = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, read_only=True)
    shipments = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('id', 'number', 'tracking_token', 'customer_name', 'email', 'phone', 'shipping_address',
                  'billing_address', 'status', 'payment_status', 'currency', 'subtotal',
                  'discount_total', 'shipping_total', 'cod_total', 'tax_total', 'grand_total', 'coupon_code', 'delivery_quote',
                  'customer_note', 'created_at', 'updated_at', 'items', 'payments', 'shipments',
                  'history', 'reservation_expires_at','stock_confirmation_pending')

    def get_payments(self, obj):
        return [{'id': p.pk, 'method': p.method, 'amount': p.amount, 'status': p.status,
                 'transaction_id': p.transaction_id, 'created_at': p.created_at} for p in obj.payments.all()]

    def get_shipments(self, obj):
        return [{'carrier': s.carrier, 'tracking_number': s.tracking_number, 'tracking_url': s.tracking_url,
                 'status': s.status, 'shipped_at': s.shipped_at, 'delivered_at': s.delivered_at} for s in obj.shipments.all()]

    def get_history(self, obj):
        return [{'status': h.status, 'note': h.note, 'created_at': h.created_at} for h in obj.history.all()]


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ('customer_id', 'is_approved', 'created_at', 'updated_at')

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return value


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommerceNotification
        fields = '__all__'


class InventoryMovementSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source='variant.sku', read_only=True)

    class Meta:
        model = InventoryMovement
        fields = '__all__'

