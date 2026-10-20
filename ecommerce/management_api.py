"""Staff storefront tools. Existing order/payment state machines stay authoritative."""
from io import BytesIO
import re
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import serializers, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (Brand, Category, CommerceNotification, Coupon, ImportJob, InventoryMovement,
                     Order, Payment, Product, ProductImage, ProductVariant, Review, Shipment, Book, DeliverySettings)
from .permissions import IsCommerceAdmin
from .pricing import calculate_price
from .delivery_rates import listing_defaults
from .cost_defaults import RESEARCH_NOTES
from .serializers import ProductDetailSerializer, ProductVariantSerializer, ProductImageSerializer, ShipmentSerializer
from .views import (AdminOrderViewSet, AdminPaymentViewSet, AdminProductViewSet,
                    CommerceAdminAuthMixin, StorefrontProductPagination)


MODELS = {model._meta.model_name: model for model in (
    Product, ProductVariant, ProductImage, Category, Brand, Order, Payment, InventoryMovement,
    Shipment, Coupon, Review, CommerceNotification, ImportJob, Book, DeliverySettings,
)}


def permitted(user, model, action):
    return bool(user and user.is_authenticated and user.is_active and user.is_staff and (
        user.is_superuser or user.has_perm(f'ecommerce.{action}_{model._meta.model_name}')
    ))


class ManagementAccessView(CommerceAdminAuthMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        staff = bool(request.user.is_authenticated and request.user.is_active and request.user.is_staff)
        return Response({'allowed': staff, 'authenticated': bool(request.user.is_authenticated), 'permissions': {
            name: {action: permitted(request.user, model, action) for action in ('view', 'add', 'change', 'delete')}
            for name, model in MODELS.items()
        } if staff else {}})


class ManagedVariantSerializer(ProductVariantSerializer):
    id = serializers.IntegerField(required=False, min_value=1)
    sku = serializers.CharField(max_length=120)  # uniqueness checked with the nested instance below
    stock = serializers.IntegerField(min_value=0)
    price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    compare_at_price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    cost_price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    expected_stock = serializers.IntegerField(required=False, min_value=0, write_only=True)

class PricingPreviewView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = ProductVariant
    permission_requirements = {'POST': ((ProductVariant, 'view'),)}

    def get(self, request):
        costs, estimated = listing_defaults(DeliverySettings.current())
        return Response({'costs':costs, 'estimated_weight':estimated, 'research':RESEARCH_NOTES})

    def post(self, request):
        if not isinstance(request.data, dict): raise ValidationError('Supply a JSON object.')
        if 'costs' in request.data and not isinstance(request.data['costs'],dict): raise ValidationError('Costs must be an object.')
        use_defaults = serializers.BooleanField().run_validation(request.data.get('use_defaults', not request.data.get('costs')))
        grams = serializers.IntegerField(min_value=0,max_value=1000000).run_validation(request.data.get('weight_grams',0))
        try:
            costs, estimated = listing_defaults(DeliverySettings.current(), grams) if use_defaults else (request.data.get('costs',{}), False)
            result = calculate_price(request.data.get('source_cost'), costs)
            result.update(use_defaults=use_defaults, weight_grams=grams or (1000 if use_defaults else 0), estimated_weight=estimated)
        except ValueError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response(result)


class ManagedImageSerializer(ProductImageSerializer):
    id = serializers.IntegerField(required=False, min_value=1)
    variant_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    url = serializers.CharField(max_length=1000)

    def validate_url(self, value):
        # Uploaded files stay same-origin through the Windows dev proxy and
        # production subdomains; external catalog photos still require a URL.
        if value.startswith('/manage/media/ecommerce/products/') and '..' not in value and '//' not in value and re.fullmatch(r'/[\w./-]+', value):
            return value
        return serializers.URLField(max_length=1000).run_validation(value)


class ManagedProductSerializer(ProductDetailSerializer):
    variants = ManagedVariantSerializer(many=True, required=False)
    images = ManagedImageSerializer(many=True, required=False)

    def validate(self, data):
        user = self.context['request'].user
        if self.instance is None and not data.get('variants'):
            raise ValidationError({'variants': 'Add at least one priced variant.'})
        for field, model in (('variants', ProductVariant), ('images', ProductImage)):
            if field not in data:
                continue
            ids, skus = set(), set()
            for row in data[field]:
                row_id = row.get('id')
                current = None
                if row_id:
                    current = model.objects.using('ecommerce').filter(pk=row_id, product_id=self.instance.pk).first() if self.instance else None
                    if row_id in ids or current is None:
                        raise ValidationError({field: 'A record does not belong to this product or is repeated.'})
                    ids.add(row_id)
                if not permitted(user, model, 'change' if row_id else 'add'):
                    raise PermissionDenied(f'Permission to manage {field} is required.')
                if field == 'variants':
                    if not row_id and ('sku' not in row or 'price' not in row):
                        raise ValidationError({'variants': 'Every new variant needs a SKU and price.'})
                    sku = row.get('sku', current.sku if current else '')
                    if sku in skus or ProductVariant.objects.using('ecommerce').filter(sku=sku).exclude(pk=row_id).exists():
                        raise ValidationError({'variants': f'SKU already exists: {sku}'})
                    skus.add(sku)
                elif row.get('variant_id') and (not self.instance or not self.instance.variants.filter(pk=row['variant_id']).exists()):
                    raise ValidationError({'images': 'Image variant must belong to this product.'})
            if self.instance:
                omitted = model.objects.using('ecommerce').filter(product=self.instance).exclude(pk__in=ids).exists()
                # Variants with historic orders are deactivated, never deleted.
                required = 'change' if field == 'variants' else 'delete'
                if omitted and not permitted(user, model, required):
                    raise PermissionDenied(f'Permission to remove {field} is required.')
        return data

    @transaction.atomic(using='ecommerce')
    def create(self, validated_data):
        return self._save(None, validated_data)

    @transaction.atomic(using='ecommerce')
    def update(self, instance, validated_data):
        instance = Product.objects.using('ecommerce').select_for_update().get(pk=instance.pk)
        return self._save(instance, validated_data)

    def _save(self, instance, data):
        variants, images = data.pop('variants', None), data.pop('images', None)
        product = super().update(instance, data) if instance else super().create(data)
        for rows, model in ((variants, ProductVariant), (images, ProductImage)):
            if rows is None:
                continue
            kept = []
            for values in rows:
                row_id = values.pop('id', None)
                row = model.objects.using('ecommerce').select_for_update().get(pk=row_id, product=product) if row_id else model(product=product)
                before = row.stock if model is ProductVariant and row_id else 0
                expected_stock = values.pop('expected_stock', None)
                if expected_stock is not None and row_id and before != expected_stock:
                    raise ValidationError({'variants': 'Stock changed while you were editing. Refresh this product before changing its stock.'})
                for key, value in values.items():
                    setattr(row, key, value)
                row.save(using='ecommerce')
                kept.append(row.pk)
                if model is ProductVariant and row.stock != before:
                    InventoryMovement.objects.using('ecommerce').create(
                        variant=row, quantity=row.stock - before, reason='adjustment',
                        actor_id=self.context['request'].user.pk, note='Product editor stock update',
                    )
            missing = model.objects.using('ecommerce').filter(product=product).exclude(pk__in=kept)
            if model is ProductVariant:
                missing.update(is_active=False)
            else:
                missing.delete()
        # Prefetched objects are stale after nested writes.
        product._prefetched_objects_cache = {}
        return product


class ManagedProductViewSet(AdminProductViewSet):
    serializer_class = ManagedProductSerializer
    pagination_class = StorefrontProductPagination

    def perform_create(self, serializer):
        self._save_checked(serializer)

    def perform_update(self, serializer):
        self._save_checked(serializer)

    def _save_checked(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise ValidationError('This slug or SKU already exists. Refresh and use a unique value.')

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(variants__sku__icontains=search)).distinct()
        status = self.request.query_params.get('status')
        return qs.filter(status=status) if status else qs


class ProductImageUploadView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = ProductImage
    permission_requirements = {'POST': ((ProductImage, 'add'),)}

    def post(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded or uploaded.size > 5 * 1024 * 1024:
            raise ValidationError({'file': 'Choose a JPG, PNG or WebP image up to 5 MB.'})
        try:
            with Image.open(uploaded) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > 20_000_000:
                    raise ValueError
                image.load()
                image = ImageOps.exif_transpose(image)
                image.thumbnail((2400, 2400))
                output = BytesIO()
                has_alpha = 'A' in image.getbands() or 'transparency' in image.info
                image.convert('RGBA' if has_alpha else 'RGB').save(output, format='WEBP', quality=90)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise ValidationError({'file': 'This is not a supported, valid product image.'})
        name = default_storage.save(f'ecommerce/products/{timezone.now():%Y/%m}/{uuid4().hex}.webp', ContentFile(output.getvalue()))
        url = default_storage.url(name).replace('/media/', '/manage/media/', 1)
        return Response({'url': url}, status=201)


class StaffRecordViewSet(CommerceAdminAuthMixin, viewsets.ModelViewSet):
    permission_classes = [IsCommerceAdmin]
    pagination_class = StorefrontProductPagination
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filter_backends = [SearchFilter]


class CategoryManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

    def validate_parent(self, parent):
        original = parent
        seen = {self.instance.pk} if self.instance else set()
        while parent:
            if parent.pk in seen:
                raise ValidationError('A category cannot contain itself or create a parent cycle.')
            seen.add(parent.pk)
            parent = parent.parent
        return original


class CategoryManageViewSet(StaffRecordViewSet):
    queryset = Category.objects.using('ecommerce').all()
    serializer_class = CategoryManageSerializer
    permission_model = Category
    search_fields = ['name', 'slug', 'description']


class BrandManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'


class BrandManageViewSet(StaffRecordViewSet):
    queryset = Brand.objects.using('ecommerce').all()
    serializer_class = BrandManageSerializer
    permission_model = Brand
    search_fields = ['name', 'slug']


class CouponManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = '__all__'
        read_only_fields = ('used_count',)

    def validate(self, data):
        value = data.get('value', getattr(self.instance, 'value', 0))
        kind = data.get('discount_type', getattr(self.instance, 'discount_type', 'fixed'))
        if value < 0 or (kind == 'percent' and value > 100):
            raise ValidationError('Discount must be non-negative; percentages cannot exceed 100.')
        start, end = (data.get(k, getattr(self.instance, k, None)) for k in ('starts_at', 'ends_at'))
        if start and end and end < start:
            raise ValidationError('End date must be after the start date.')
        return data


class CouponManageViewSet(StaffRecordViewSet):
    queryset = Coupon.objects.using('ecommerce').all().order_by('-id')
    serializer_class = CouponManageSerializer
    permission_model = Coupon
    search_fields = ['code']


class ShipmentManageSerializer(ShipmentSerializer):
    status = serializers.ChoiceField(choices=['preparing', 'shipped', 'delivered', 'returned'])

    def validate(self, data):
        target = data.get('status', 'preparing')
        if target != 'preparing' and (not self.instance or target != self.instance.status):
            user = self.context['request'].user
            if not permitted(user, Order, 'change'):
                raise PermissionDenied('Changing shipment status also requires permission to change orders.')
        return data

    def create(self, validated_data):
        from .order_service import save_shipment
        return save_shipment(None, validated_data, self.context['request'].user.pk)

    def update(self, instance, validated_data):
        from .order_service import save_shipment
        return save_shipment(instance, validated_data, self.context['request'].user.pk)

    def validate_order(self, order):
        if self.instance and self.instance.order_id != order.pk:
            raise ValidationError('An existing shipment cannot be moved to a different order.')
        return order


class ShipmentManageViewSet(StaffRecordViewSet):
    queryset = Shipment.objects.using('ecommerce').select_related('order').all()
    serializer_class = ShipmentManageSerializer
    permission_model = Shipment
    search_fields = ['carrier', 'tracking_number', 'order__number']


class ReviewManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ('product', 'customer_id', 'customer_name', 'rating', 'title', 'body')


class ReviewManageViewSet(StaffRecordViewSet):
    queryset = Review.objects.using('ecommerce').all()
    serializer_class = ReviewManageSerializer
    permission_model = Review
    http_method_names = ['get', 'patch', 'head', 'options']
    search_fields = ['customer_name', 'title', 'body']


class ImportManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJob
        fields = '__all__'


class ImportManageViewSet(StaffRecordViewSet):
    queryset = ImportJob.objects.using('ecommerce').all().order_by('-id')
    serializer_class = ImportManageSerializer
    permission_model = ImportJob
    http_method_names = ['get', 'head', 'options']
    search_fields = ['filename']


class NotificationManageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommerceNotification
        fields = '__all__'
        read_only_fields = tuple(f.name for f in CommerceNotification._meta.fields if f.name != 'is_read')


class NotificationManageViewSet(StaffRecordViewSet):
    queryset = CommerceNotification.objects.using('ecommerce').filter(admin_only=True)
    serializer_class = NotificationManageSerializer
    permission_model = CommerceNotification
    http_method_names = ['get', 'patch', 'head', 'options']
    search_fields = ['title', 'message']


class ManagedOrderViewSet(AdminOrderViewSet):
    pagination_class = StorefrontProductPagination

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(number__icontains=search) | Q(customer_name__icontains=search) | Q(phone__icontains=search))
        return qs


class ManagedPaymentViewSet(AdminPaymentViewSet):
    pagination_class = StorefrontProductPagination

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('status'):
            qs = qs.filter(status=self.request.query_params['status'])
        return qs


class VariantManageViewSet(StaffRecordViewSet):
    queryset = ProductVariant.objects.using('ecommerce').select_related('product').all()
    serializer_class = ProductVariantSerializer
    permission_model = ProductVariant
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search', '').strip()
        return qs.filter(Q(sku__icontains=search) | Q(product__name__icontains=search)) if search else qs
