from rest_framework import serializers

from .models import (
    Brand, Cart, CartItem, Category, CommerceNotification, InventoryMovement,
    Order, OrderItem, OrderStatusHistory, Payment, Product, ProductImage,
    ProductVariant, Review, Shipment,
)


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
    class Meta:
        model = ProductVariant
        fields = '__all__'
        read_only_fields = ('product', 'created_at', 'updated_at')


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    compare_at_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True, allow_null=True)
    stock = serializers.IntegerField(read_only=True)
    image_url = serializers.CharField(read_only=True)
    default_variant_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'short_description', 'category_id', 'category_name',
            'brand_id', 'brand_name', 'status', 'featured', 'tags', 'price',
            'compare_at_price', 'stock', 'image_url', 'is_sample', 'source_url',
            'default_variant_id',
        )


class ProductDetailSerializer(serializers.ModelSerializer):
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


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    variant_title = serializers.CharField(source='variant.title', read_only=True)
    sku = serializers.CharField(source='variant.sku', read_only=True)
    unit_price = serializers.DecimalField(source='variant.price', max_digits=14, decimal_places=2, read_only=True)
    image_url = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ('id', 'variant_id', 'quantity', 'product_name', 'variant_title', 'sku', 'unit_price', 'image_url', 'line_total')

    def get_image_url(self, obj):
        image = obj.variant.images.first() or obj.variant.product.images.first()
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


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('confirmed_by', 'confirmed_at', 'created_at', 'updated_at')


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = '__all__'


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = '__all__'


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    shipments = ShipmentSerializer(many=True, read_only=True)
    history = OrderStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = '__all__'


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

