from contextlib import nullcontext
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, DecimalField, F, OuterRef, Prefetch, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpResponse, HttpResponseRedirect
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cheradip.models import Customer, MembershipProgress, PackageSubscription, RewardsWallet
from cheradip.views import BearerTokenAuthentication
from cheradip.wallet_service import deduct_wallet_coins

from .csv_import import import_products, sample_csv_text
from .book_catalog import sync_book_catalog
from .book_builder import build_book_asset
from .models import (
    Book, BookAsset, BookBuildJob, Brand, Cart, CartItem, Category, CommerceNotification, Coupon, ImportJob,
    InventoryMovement, Order, OrderItem, OrderStatusHistory, Payment, Product,
    ProductImage, ProductVariant, Review, Shipment,
)
from .permissions import IsCommerceAdmin
from .serializers import (
    BookAssetSerializer, BookBuildJobSerializer, BookSerializer, BrandSerializer, CartSerializer, CategorySerializer, InventoryMovementSerializer,
    NotificationSerializer, OrderSerializer, PaymentSerializer, ProductDetailSerializer,
    ProductListSerializer, ReviewSerializer,
)


def _user_id(request):
    user = getattr(request, 'user', None)
    return user.pk if user and user.is_authenticated else None


COINS_PER_TAKA = Decimal('100')


def _wallet_coins(customer):
    settings = customer.settings if isinstance(customer.settings, dict) else {}
    try:
        return max(0, int(settings.get('balance', 0) or 0))
    except (TypeError, ValueError):
        return 0


def _taka_to_coins(amount):
    return int((Decimal(amount) * COINS_PER_TAKA).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _coins_to_taka(coins):
    return (Decimal(max(0, int(coins))) / COINS_PER_TAKA).quantize(Decimal('0.01'))


def _product_queryset(include_inactive=False):
    first_variant = ProductVariant.objects.using('ecommerce').filter(product_id=OuterRef('pk'), is_active=True).order_by('id')
    first_image = ProductImage.objects.using('ecommerce').filter(product_id=OuterRef('pk')).order_by('position', 'id')
    qs = Product.objects.using('ecommerce').select_related('category', 'brand').annotate(
        price=Subquery(first_variant.values('price')[:1], output_field=DecimalField(max_digits=14, decimal_places=2)),
        compare_at_price=Subquery(first_variant.values('compare_at_price')[:1], output_field=DecimalField(max_digits=14, decimal_places=2)),
        stock=Coalesce(Sum('variants__stock', filter=Q(variants__is_active=True)), 0),
        image_url=Subquery(first_image.values('url')[:1]),
        default_variant_id=Subquery(first_variant.values('id')[:1]),
    )
    return qs if include_inactive else qs.filter(status='active')


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return Category.objects.using('ecommerce').filter(is_active=True).annotate(
            product_count=Count('products', filter=Q(products__status='active'), distinct=True)
        )


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return Brand.objects.using('ecommerce').filter(is_active=True)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == 'retrieve' else ProductListSerializer

    def get_queryset(self):
        qs = _product_queryset()
        params = self.request.query_params
        search = (params.get('search') or '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(tags__icontains=search) | Q(variants__sku__icontains=search)).distinct()
        if params.get('category'):
            qs = qs.filter(Q(category__slug=params['category']) | Q(category__parent__slug=params['category']))
        if params.get('brand'):
            qs = qs.filter(brand__slug=params['brand'])
        if params.get('featured') in {'1', 'true'}:
            qs = qs.filter(featured=True)
        if params.get('min_price'):
            qs = qs.filter(price__gte=params['min_price'])
        if params.get('max_price'):
            qs = qs.filter(price__lte=params['max_price'])
        ordering = params.get('ordering')
        if ordering in {'price', '-price', 'name', '-name', 'created_at', '-created_at'}:
            qs = qs.order_by(ordering)
        return qs


class BookViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BookSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        digital_variant = ProductVariant.objects.using('ecommerce').filter(
            product_id=OuterRef('product_id'), sku__endswith='-DIGITAL', is_active=True,
        )
        hard_copy_variant = ProductVariant.objects.using('ecommerce').filter(
            product_id=OuterRef('product_id'), sku__endswith='-HARDCOPY', is_active=True,
        )
        qs = Book.objects.using('ecommerce').filter(status='published').annotate(
            storefront_digital_variant_id=Subquery(digital_variant.values('id')[:1]),
            storefront_hard_copy_variant_id=Subquery(hard_copy_variant.values('id')[:1]),
        ).prefetch_related(
            Prefetch(
                'assets',
                queryset=BookAsset.objects.using('ecommerce').filter(asset_type__in=('sample', 'video')),
                to_attr='storefront_public_assets',
            ),
            Prefetch(
                'assets',
                queryset=BookAsset.objects.using('ecommerce').filter(asset_type='ebook'),
                to_attr='storefront_ebook_assets',
            ),
        )
        params = self.request.query_params
        if params.get('book_type'):
            qs = qs.filter(book_type=params['book_type'])
        if params.get('audience'):
            qs = qs.filter(audience=params['audience'])
        if params.get('language'):
            qs = qs.filter(language__iexact=params['language'])
        copy_type = params.get('copy_type', '').lower()
        if copy_type in {'hard', 'both'}:
            qs = qs.filter(hard_copy_available=True)
        if copy_type in {'soft', 'both'}:
            qs = qs.filter(
                product__variants__sku__endswith='-DIGITAL',
                product__variants__is_active=True,
            )
        if params.get('hard_copy') in {'1', 'true', 'yes'}:
            qs = qs.filter(hard_copy_available=True)
        if params.get('search'):
            search = params['search'].strip()
            qs = qs.filter(
                Q(title__icontains=search) | Q(title_bn__icontains=search) |
                Q(author__icontains=search) | Q(isbn__icontains=search) |
                Q(tags__icontains=search) | Q(description__icontains=search)
            )
        ordering = params.get('ordering', '-featured')
        allowed = {'title', '-title', 'digital_price', '-digital_price', 'created_at', '-created_at', '-featured'}
        return qs.order_by(ordering if ordering in allowed else '-featured', '-created_at').distinct()


def _paid_order(request):
    order_number = (request.query_params.get('order_number') or '').strip()
    tracking_token = (request.query_params.get('tracking_token') or '').strip()
    if not order_number or not tracking_token:
        return None
    return Order.objects.using('ecommerce').prefetch_related('items').filter(
        number=order_number, tracking_token=tracking_token,
        payment_status='paid', status='completed',
    ).first()


class DigitalLibraryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        order = _paid_order(request)
        if not order:
            return Response({'detail': 'A paid order and valid tracking token are required.'}, status=status.HTTP_403_FORBIDDEN)
        product_ids = list(order.items.values_list('product_id', flat=True))
        books = Book.objects.using('ecommerce').filter(product_id__in=product_ids).prefetch_related('assets')
        return Response([
            {
                'title': book.title, 'title_bn': book.title_bn, 'slug': book.slug,
                'formats': list(book.assets.filter(asset_type='ebook').values_list('file_format', flat=True)),
                'download_url': (
                    f'/api/ecommerce/digital-library/{book.slug}/download/'
                    f'?order_number={order.number}&tracking_token={order.tracking_token}'
                ),
            }
            for book in books if book.assets.filter(asset_type='ebook', is_downloadable=True).exists()
        ])


class DigitalBookDownloadView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        order = _paid_order(request)
        if not order:
            return Response({'detail': 'A paid order and valid tracking token are required.'}, status=status.HTTP_403_FORBIDDEN)
        product_ids = order.items.values_list('product_id', flat=True)
        book = Book.objects.using('ecommerce').filter(slug=slug, product_id__in=product_ids).first()
        if not book:
            return Response({'detail': 'This book is not included in the paid order.'}, status=status.HTTP_404_NOT_FOUND)
        asset = book.assets.filter(asset_type='ebook', is_downloadable=True).order_by('-is_primary', 'sort_order', 'id').first()
        if not asset:
            return Response({'detail': 'The ebook file is not available yet.'}, status=status.HTTP_404_NOT_FOUND)
        if asset.file:
            return FileResponse(asset.file.open('rb'), as_attachment=True, filename=asset.file.name.rsplit('/', 1)[-1])
        if asset.external_url:
            return HttpResponseRedirect(asset.external_url)
        return Response({'detail': 'The ebook file is not available yet.'}, status=status.HTTP_404_NOT_FOUND)


class CartView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]

    def _cart(self, token):
        return Cart.objects.using('ecommerce').prefetch_related('items__variant__product__images').filter(token=token, checked_out=False).first()

    def get(self, request, token=None):
        cart = self._cart(token) if token else None
        if cart is None:
            cart = Cart.objects.using('ecommerce').create(customer_id=_user_id(request))
        elif _user_id(request) and not cart.customer_id:
            cart.customer_id = _user_id(request)
            cart.save(using='ecommerce', update_fields=['customer_id', 'updated_at'])
        return Response(CartSerializer(cart).data)

    def post(self, request, token=None):
        cart = self._cart(token) if token else None
        if cart is None:
            cart = Cart.objects.using('ecommerce').create(customer_id=_user_id(request), email=request.data.get('email', ''))
        elif _user_id(request) and not cart.customer_id:
            cart.customer_id = _user_id(request)
            cart.save(using='ecommerce', update_fields=['customer_id', 'updated_at'])
        variant = ProductVariant.objects.using('ecommerce').select_related('product').filter(pk=request.data.get('variant_id'), is_active=True, product__status='active').first()
        if not variant:
            return Response({'detail': 'Product variant not found.'}, status=status.HTTP_404_NOT_FOUND)
        quantity = max(1, int(request.data.get('quantity', 1)))
        if not variant.allow_backorder and quantity > variant.stock:
            return Response({'detail': 'Requested quantity is not available.'}, status=status.HTTP_400_BAD_REQUEST)
        item, created = CartItem.objects.using('ecommerce').get_or_create(cart=cart, variant=variant, defaults={'quantity': quantity})
        if not created:
            item.quantity = quantity
            item.save(using='ecommerce')
        cart._prefetched_objects_cache = {}
        return Response(CartSerializer(cart).data)

    def delete(self, request, token=None):
        cart = self._cart(token)
        if not cart:
            return Response(status=status.HTTP_204_NO_CONTENT)
        item_id = request.query_params.get('item_id')
        if item_id:
            cart.items.filter(pk=item_id).delete()
        else:
            cart.items.all().delete()
        cart._prefetched_objects_cache = {}
        return Response(CartSerializer(cart).data)


class CheckoutView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        cart = Cart.objects.using('ecommerce').prefetch_related('items__variant__product__images').filter(
            token=request.data.get('cart_token'), checked_out=False
        ).first()
        if not cart or not cart.items.exists():
            return Response({'detail': 'Cart is empty or unavailable.'}, status=status.HTTP_400_BAD_REQUEST)

        required = ['customer_name', 'email', 'phone', 'shipping_address']
        missing = [field for field in required if not request.data.get(field)]
        if missing:
            return Response({'detail': 'Missing fields: ' + ', '.join(missing)}, status=status.HTTP_400_BAD_REQUEST)

        payment_method = (request.data.get('payment_method') or 'cod').strip().lower()
        if payment_method == 'wallet' and not getattr(request.user, 'is_authenticated', False):
            return Response({'detail': 'Please sign in to pay with your Cheradip Wallet.'}, status=status.HTTP_401_UNAUTHORIZED)

        wallet_transaction = transaction.atomic(using='default') if payment_method == 'wallet' else nullcontext()
        with wallet_transaction:
            with transaction.atomic(using='ecommerce'):
                subtotal = Decimal('0')
                locked = []
                for cart_item in cart.items.all():
                    variant = ProductVariant.objects.using('ecommerce').select_for_update().select_related('product').get(pk=cart_item.variant_id)
                    if not variant.allow_backorder and cart_item.quantity > variant.stock:
                        return Response({'detail': f'Insufficient stock for {variant.sku}.'}, status=status.HTTP_409_CONFLICT)
                    subtotal += variant.price * cart_item.quantity
                    locked.append((cart_item, variant))

                # Shipping and discounts are always calculated by the server.
                requires_shipping = any(variant.requires_shipping for _, variant in locked)
                shipping_total = Decimal('0') if not requires_shipping or subtotal >= Decimal('3000') else Decimal('80')
                discount_total = Decimal('0')
                coupon = None
                coupon_code = (request.data.get('coupon_code') or '').strip().upper()
                if coupon_code:
                    now = timezone.now()
                    coupon = Coupon.objects.using('ecommerce').select_for_update().filter(code__iexact=coupon_code, is_active=True).first()
                    if coupon and (not coupon.starts_at or coupon.starts_at <= now) and (not coupon.ends_at or coupon.ends_at >= now) and subtotal >= coupon.minimum_order and (coupon.usage_limit is None or coupon.used_count < coupon.usage_limit):
                        if coupon.discount_type == 'percent':
                            discount_total = subtotal * coupon.value / Decimal('100')
                        elif coupon.discount_type == 'fixed':
                            discount_total = min(subtotal, coupon.value)
                        elif coupon.discount_type == 'shipping':
                            shipping_total = Decimal('0')
                    else:
                        coupon = None

                grand_total = subtotal - discount_total + shipping_total
                wallet_balance_taka = None
                reference_balance_taka = None
                reference_used_taka = Decimal('0')
                if payment_method == 'wallet':
                    customer = Customer.objects.select_for_update().get(pk=request.user.pk)
                    balance_coins = _wallet_coins(customer)
                    required_coins = _taka_to_coins(grand_total)
                    if balance_coins < required_coins:
                        return Response({
                            'detail': 'Insufficient Cheradip Wallet balance. Please recharge and try again.',
                            'requiredTaka': float(grand_total),
                            'availableTaka': float(_coins_to_taka(balance_coins)),
                            'shortfallTaka': float(_coins_to_taka(required_coins - balance_coins)),
                        }, status=status.HTTP_402_PAYMENT_REQUIRED)
                    wallet_result = deduct_wallet_coins(customer, required_coins)
                    wallet_balance_taka = wallet_result['remaining_taka']
                    reference_used_taka = wallet_result['reference_used_taka']
                    reference_balance_taka = wallet_result['reference_balance_taka']

                if coupon:
                    coupon.used_count += 1
                    coupon.save(using='ecommerce', update_fields=['used_count', 'updated_at'])

                paid_with_wallet = payment_method == 'wallet'
                order = Order.objects.using('ecommerce').create(
                    customer_id=_user_id(request), customer_name=request.data['customer_name'],
                    email=request.data['email'], phone=request.data['phone'],
                    shipping_address=request.data['shipping_address'],
                    billing_address=request.data.get('billing_address') or request.data['shipping_address'],
                    # Products and eBooks always await manual administrative fulfilment,
                    # even when their payment has already been received.
                    status='pending',
                    payment_status='paid' if paid_with_wallet else 'unpaid',
                    confirmed_at=None,
                    subtotal=subtotal, discount_total=discount_total, shipping_total=shipping_total,
                    grand_total=grand_total, coupon_code=coupon_code,
                    customer_note=request.data.get('customer_note', ''),
                )
                for cart_item, variant in locked:
                    image = variant.images.first() or variant.product.images.first()
                    OrderItem.objects.using('ecommerce').create(
                        order=order, product_id=variant.product_id, variant_id=variant.id,
                        product_name=variant.product.name, variant_title=variant.title, sku=variant.sku,
                        image_url=image.url if image else '', quantity=cart_item.quantity,
                        unit_price=variant.price, line_total=variant.price * cart_item.quantity,
                    )
                    variant.stock -= cart_item.quantity
                    variant.save(using='ecommerce', update_fields=['stock', 'updated_at'])
                    InventoryMovement.objects.using('ecommerce').create(
                        variant=variant, quantity=-cart_item.quantity, reason='sale', reference=order.number,
                        actor_id=_user_id(request),
                    )
                    if variant.stock <= variant.low_stock_threshold:
                        CommerceNotification.objects.using('ecommerce').create(
                            kind='inventory', title='Low stock', message=f'{variant.sku} has {variant.stock} item(s) left.',
                            link='/admin/ecommerce/productvariant/', admin_only=True,
                        )
                if paid_with_wallet:
                    payment_note = 'Paid automatically from Cheradip Wallet.'
                    if reference_used_taka:
                        payment_note += f' Reference balance used first: Tk {reference_used_taka:.2f}.'
                    Payment.objects.using('ecommerce').create(
                        order=order, method='wallet', amount=grand_total,
                        transaction_id=f'WALLET-{order.number}', status='confirmed',
                        confirmed_by=request.user.pk, confirmed_at=timezone.now(),
                        note=payment_note,
                    )
                OrderStatusHistory.objects.using('ecommerce').create(
                    order=order, status='pending',
                    note=(
                        'Payment received; waiting for admin to mark the order completed.'
                        if paid_with_wallet else 'Order placed; waiting for payment and admin approval.'
                    ),
                    actor_id=_user_id(request),
                )
                CommerceNotification.objects.using('ecommerce').create(
                    kind='order', title=f'New order {order.number}', message=f'Order total: {order.grand_total} {order.currency}',
                    link=f'/admin/ecommerce/order/{order.pk}/change/', admin_only=True,
                )
                cart.checked_out = True
                if _user_id(request) and not cart.customer_id:
                    cart.customer_id = _user_id(request)
                cart.save(using='ecommerce', update_fields=['checked_out', 'customer_id', 'updated_at'])

        payload = OrderSerializer(order).data
        if wallet_balance_taka is not None:
            payload['walletBalanceTaka'] = float(wallet_balance_taka)
            payload['referenceBalanceTaka'] = float(reference_balance_taka or Decimal('0'))
            payload['referenceUsedTaka'] = float(reference_used_taka)
        return Response(payload, status=status.HTTP_201_CREATED)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]
    lookup_field = 'number'

    def get_queryset(self):
        qs = Order.objects.using('ecommerce').prefetch_related('items', 'payments', 'shipments', 'history')
        user = getattr(self.request, 'user', None)
        if user and user.is_authenticated:
            return qs if user.is_staff or user.is_superuser else qs.filter(customer_id=user.pk)
        tracking_token = self.request.query_params.get('tracking_token')
        if tracking_token:
            return qs.filter(tracking_token=tracking_token)
        return qs.none()


class AccountHistoryView(APIView):
    """Meaningful purchases only: packages and commerce orders, never small coin deductions."""

    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        customer = request.user
        coin_balance = _wallet_coins(customer)
        rewards_wallet, _ = RewardsWallet.objects.get_or_create(customer=customer)
        primary_audience = 'student' if customer.acctype == 'Student' else 'teacher'
        progress = MembershipProgress.objects.filter(
            customer=customer, audience=primary_audience,
        ).first()
        package_rows = PackageSubscription.objects.filter(
            customer=customer,
        ).select_related('plan').order_by('-created_at')[:100]
        order_rows = Order.objects.using('ecommerce').filter(
            customer_id=customer.pk,
        ).prefetch_related('items', 'payments').order_by('-created_at')[:100]

        packages = [{
            'id': row.pk,
            'orderNumber': row.order_number,
            'orderStatus': row.get_order_status_display(),
            'planCode': row.plan.code,
            'title': f'{row.plan.name} · {row.plan.get_track_display()}',
            'audience': row.plan.get_audience_display(),
            'status': row.get_status_display(),
            'amountTaka': float(row.payable_amount),
            'startsAt': row.starts_at.isoformat() if row.starts_at else None,
            'endsAt': row.ends_at.isoformat() if row.ends_at else None,
            'createdAt': row.created_at.isoformat(),
        } for row in package_rows]

        orders = []
        for row in order_rows:
            payment = next(iter(row.payments.all()), None)
            orders.append({
                'number': row.number,
                'status': row.get_status_display(),
                'paymentStatus': row.get_payment_status_display(),
                'paymentMethod': payment.get_method_display() if payment else 'Cash on delivery',
                'totalTaka': float(row.grand_total),
                'createdAt': row.created_at.isoformat(),
                'items': [{
                    'name': item.product_name,
                    'variant': item.variant_title,
                    'quantity': item.quantity,
                    'lineTotalTaka': float(item.line_total),
                    'isBook': item.sku.startswith('BOOK-'),
                } for item in row.items.all()],
            })

        return Response({
            'profile': {
                'fullName': customer.fullName,
                'accountType': customer.get_acctype_display(),
                'badge': progress.badge if progress else 'None',
                'profileImageUrl': '/manage' + customer.profile_image.url if customer.profile_image else None,
            },
            'wallet': {
                'coinBalance': coin_balance,
                'balanceTaka': float(_coins_to_taka(coin_balance)),
                'referenceBalanceTaka': float(rewards_wallet.available_taka),
            },
            'packages': packages,
            'orders': orders,
        })


class OrderTrackingView(APIView):
    """Track a package, product, or book order through one customer-facing ID."""

    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, order_number):
        normalized = str(order_number or '').strip()
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            package = PackageSubscription.objects.filter(
                order_number__iexact=normalized,
                customer=user,
            ).select_related('plan').first()
            if package:
                return Response({
                    'kind': 'package',
                    'number': package.order_number,
                    'status': package.order_status,
                    'status_label': package.get_order_status_display(),
                    'payment_status': 'paid',
                    'payment_status_label': 'Paid',
                    'title': f'{package.plan.name} · {package.plan.get_track_display()}',
                    'grand_total': str(package.payable_amount),
                    'created_at': package.created_at.isoformat(),
                    'history': [{
                        'status': package.get_order_status_display(),
                        'note': 'Cheradip package activated successfully using the wallet.',
                        'created_at': package.created_at.isoformat(),
                    }],
                    'items': [{
                        'product_name': f'{package.plan.name} package',
                        'variant_title': package.plan.get_track_display(),
                        'quantity': 1,
                        'line_total': str(package.payable_amount),
                    }],
                })

        commerce = Order.objects.using('ecommerce').prefetch_related(
            'items', 'payments', 'shipments', 'history',
        ).filter(number__iexact=normalized).first()
        if not commerce:
            return Response({'detail': 'Order ID was not found.'}, status=status.HTTP_404_NOT_FOUND)
        owns_order = bool(user and user.is_authenticated and (
            user.is_staff or user.is_superuser or commerce.customer_id == user.pk
        ))
        tracking_token = (request.query_params.get('tracking_token') or '').strip()
        if not owns_order and tracking_token != commerce.tracking_token:
            return Response(
                {'detail': 'Sign in to the purchasing account or provide the private tracking token.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        payload = OrderSerializer(commerce).data
        payload.update({
            'kind': 'commerce',
            'status_label': commerce.get_status_display(),
            'payment_status_label': commerce.get_payment_status_display(),
        })
        return Response(payload)


class PaymentCreateView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]

    def post(self, request, order_number):
        order = Order.objects.using('ecommerce').filter(number=order_number).first()
        if not order:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)
        token = request.data.get('tracking_token')
        user_id = _user_id(request)
        if not ((user_id and (getattr(request.user, 'is_staff', False) or order.customer_id == user_id)) or token == order.tracking_token):
            return Response({'detail': 'Order access denied.'}, status=status.HTTP_403_FORBIDDEN)
        # The payable amount is authoritative on the order; clients cannot lower it.
        if request.data.get('method') == 'wallet':
            return Response({'detail': 'Wallet payments must be completed during checkout.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PaymentSerializer(data={**request.data, 'order': order.id, 'amount': order.grand_total})
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        order.payment_status = 'pending' if payment.method != 'cod' else 'unpaid'
        order.save(using='ecommerce', update_fields=['payment_status', 'updated_at'])
        CommerceNotification.objects.using('ecommerce').create(
            kind='payment', title=f'Payment submitted for {order.number}',
            message=f'{payment.method}: {payment.amount} {order.currency}',
            link=f'/admin/ecommerce/payment/{payment.pk}/change/', admin_only=True,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class ReviewCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, product_id):
        if not Product.objects.using('ecommerce').filter(pk=product_id, status='active').exists():
            return Response({'detail': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ReviewSerializer(data={**request.data, 'product': product_id})
        serializer.is_valid(raise_exception=True)
        review = serializer.save(customer_id=request.user.pk)
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class AdminDashboardView(APIView):
    permission_classes = [IsCommerceAdmin]

    def get(self, request):
        orders = Order.objects.using('ecommerce')
        variants = ProductVariant.objects.using('ecommerce')
        return Response({
            'products': Product.objects.using('ecommerce').count(),
            'active_products': Product.objects.using('ecommerce').filter(status='active').count(),
            'books': Book.objects.using('ecommerce').count(),
            'published_books': Book.objects.using('ecommerce').filter(status='published').count(),
            'queued_book_builds': BookBuildJob.objects.using('ecommerce').filter(status__in=['queued', 'building']).count(),
            'orders': orders.count(),
            'pending_orders': orders.filter(status='pending').count(),
            'pending_payments': Payment.objects.using('ecommerce').filter(status='pending').count(),
            'low_stock': variants.filter(stock__lte=F('low_stock_threshold'), is_active=True).count(),
            'revenue': orders.filter(payment_status='paid').aggregate(
                total=Coalesce(
                    Sum('grand_total'),
                    Decimal('0'),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )['total'],
            'unread_notifications': CommerceNotification.objects.using('ecommerce').filter(admin_only=True, is_read=False).count(),
        })


class AdminProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductDetailSerializer
    permission_classes = [IsCommerceAdmin]

    def get_queryset(self):
        return _product_queryset(include_inactive=True).prefetch_related('variants', 'images')

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        product = self.get_object()
        product.status = 'archived'
        product.save(using='ecommerce', update_fields=['status', 'updated_at'])
        return Response(ProductDetailSerializer(product).data)


class AdminBookViewSet(viewsets.ModelViewSet):
    serializer_class = BookSerializer
    permission_classes = [IsCommerceAdmin]
    lookup_field = 'slug'

    def get_queryset(self):
        return Book.objects.using('ecommerce').prefetch_related('assets', 'build_jobs').all()

    def perform_create(self, serializer):
        book = serializer.save(created_by=_user_id(self.request))
        sync_book_catalog(book)

    def perform_update(self, serializer):
        book = serializer.save()
        sync_book_catalog(book)

    @action(detail=True, methods=['post'])
    def build(self, request, slug=None):
        book = self.get_object()
        source_config = request.data.get('source_config') or book.source_config or {}
        output_format = request.data.get('output_format', 'pdf')
        if output_format not in {choice[0] for choice in BookBuildJob.OUTPUT_FORMATS}:
            return Response({'detail': 'Unsupported output format.'}, status=status.HTTP_400_BAD_REQUEST)
        book.source_config = source_config
        if request.data.get('source_type') in {choice[0] for choice in Book.SOURCE_TYPES}:
            book.source_type = request.data['source_type']
        book.save(using='ecommerce', update_fields=['source_config', 'source_type', 'updated_at'])
        job = BookBuildJob.objects.using('ecommerce').create(
            book=book, output_format=output_format, source_config=source_config,
            created_by=_user_id(request),
            message='Queued for manuscript generation from the selected question or exam sets.',
        )
        CommerceNotification.objects.using('ecommerce').create(
            kind='system', title=f'Book build started: {book.title}',
            message=f'{output_format.upper()} from {book.get_source_type_display()}',
            link=f'/admin/ecommerce/bookbuildjob/{job.pk}/change/', admin_only=True,
        )
        try:
            build_book_asset(job)
        except Exception as exc:
            return Response(
                {'detail': str(exc), 'job': BookBuildJobSerializer(job).data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sync_book_catalog(book, notify=False)
        return Response(BookBuildJobSerializer(job).data, status=status.HTTP_201_CREATED)


class AdminBookAssetViewSet(viewsets.ModelViewSet):
    serializer_class = BookAssetSerializer
    permission_classes = [IsCommerceAdmin]

    def get_queryset(self):
        qs = BookAsset.objects.using('ecommerce').select_related('book')
        return qs.filter(book_id=self.request.query_params['book']) if self.request.query_params.get('book') else qs

    def perform_create(self, serializer):
        asset = serializer.save()
        sync_book_catalog(asset.book, notify=False)
        CommerceNotification.objects.using('ecommerce').create(
            kind='system', title=f'Book file added: {asset.book.title}',
            message=f'{asset.get_asset_type_display()} · {asset.get_file_format_display()}',
            link=f'/admin/ecommerce/book/{asset.book_id}/change/', admin_only=True,
        )


class AdminBookBuildJobViewSet(viewsets.ModelViewSet):
    serializer_class = BookBuildJobSerializer
    permission_classes = [IsCommerceAdmin]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return BookBuildJob.objects.using('ecommerce').select_related('book', 'result_asset')


class AdminOrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsCommerceAdmin]
    lookup_field = 'number'
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = Order.objects.using('ecommerce').prefetch_related('items', 'payments', 'shipments', 'history')
        if self.request.query_params.get('status'):
            qs = qs.filter(status=self.request.query_params['status'])
        return qs

    def partial_update(self, request, *args, **kwargs):
        order = self.get_object()
        old_status = order.status
        new_status = request.data.get('status', old_status)
        allowed = {choice[0] for choice in Order.STATUS_CHOICES}
        if new_status not in allowed:
            return Response({'detail': 'Invalid order status.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic(using='ecommerce'):
            order.status = new_status
            order.admin_note = request.data.get('admin_note', order.admin_note)
            if new_status == 'completed':
                order.payment_status = 'paid'
            if new_status == 'confirmed' and not order.confirmed_at:
                order.confirmed_at = timezone.now()
            if new_status in {'shipped', 'delivered', 'completed'} and not order.fulfilled_at:
                order.fulfilled_at = timezone.now()
            order.save(using='ecommerce')
            if new_status != old_status:
                OrderStatusHistory.objects.using('ecommerce').create(
                    order=order, status=new_status, note=request.data.get('note', ''), actor_id=request.user.pk,
                )
                if new_status == 'cancelled':
                    for item in order.items.all():
                        variant = ProductVariant.objects.using('ecommerce').select_for_update().filter(pk=item.variant_id).first()
                        if variant:
                            variant.stock += item.quantity
                            variant.save(using='ecommerce', update_fields=['stock', 'updated_at'])
                            InventoryMovement.objects.using('ecommerce').create(
                                variant=variant, quantity=item.quantity, reason='cancel', reference=order.number, actor_id=request.user.pk,
                            )
                CommerceNotification.objects.using('ecommerce').create(
                    kind='order', title=f'Order {order.number}: {new_status}',
                    message=request.data.get('note', ''), link=f'/history?order={order.number}', customer_id=order.customer_id,
                )
        return Response(OrderSerializer(order).data)


class AdminPaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsCommerceAdmin]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return Payment.objects.using('ecommerce').select_related('order')

    def partial_update(self, request, *args, **kwargs):
        payment = self.get_object()
        new_status = request.data.get('status', payment.status)
        if new_status not in {choice[0] for choice in Payment.STATUS_CHOICES}:
            return Response({'detail': 'Invalid payment status.'}, status=status.HTTP_400_BAD_REQUEST)
        payment.status = new_status
        payment.note = request.data.get('note', payment.note)
        if new_status == 'confirmed':
            payment.confirmed_by = request.user.pk
            payment.confirmed_at = timezone.now()
        payment.save(using='ecommerce')
        order = payment.order
        order.payment_status = {'confirmed': 'paid', 'failed': 'failed', 'refunded': 'refunded'}.get(new_status, 'pending')
        order.save(using='ecommerce', update_fields=['payment_status', 'updated_at'])
        return Response(PaymentSerializer(payment).data)


class AdminInventoryView(APIView):
    permission_classes = [IsCommerceAdmin]

    def get(self, request):
        qs = InventoryMovement.objects.using('ecommerce').select_related('variant').all()[:500]
        return Response(InventoryMovementSerializer(qs, many=True).data)

    def post(self, request):
        variant = ProductVariant.objects.using('ecommerce').filter(pk=request.data.get('variant_id')).first()
        if not variant:
            return Response({'detail': 'Variant not found.'}, status=status.HTTP_404_NOT_FOUND)
        quantity = int(request.data.get('quantity', 0))
        with transaction.atomic(using='ecommerce'):
            variant = ProductVariant.objects.using('ecommerce').select_for_update().get(pk=variant.pk)
            variant.stock += quantity
            variant.save(using='ecommerce', update_fields=['stock', 'updated_at'])
            movement = InventoryMovement.objects.using('ecommerce').create(
                variant=variant, quantity=quantity, reason='adjustment',
                reference=request.data.get('reference', ''), note=request.data.get('note', ''), actor_id=request.user.pk,
            )
        return Response(InventoryMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class AdminCsvImportView(APIView):
    permission_classes = [IsCommerceAdmin]

    def post(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded:
            return Response({'detail': 'Attach a CSV file using the field "file".'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            job = import_products(uploaded, request.user.pk)
        except (UnicodeDecodeError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'id': job.id, 'status': job.status, 'total_rows': job.total_rows,
            'created': job.created_count, 'updated': job.updated_count,
            'failed': job.failed_count, 'errors': job.errors,
        }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
def sample_csv(request):
    response = HttpResponse(sample_csv_text(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="cheradip-products-sample.csv"'
    return response


class NotificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = CommerceNotification.objects.using('ecommerce').filter(
            Q(customer_id=request.user.pk) | Q(admin_only=False, customer_id__isnull=True)
        )
        if request.user.is_staff or request.user.is_superuser:
            qs = CommerceNotification.objects.using('ecommerce').all()
        return Response(NotificationSerializer(qs[:100], many=True).data)

    def patch(self, request):
        ids = request.data.get('ids') or []
        qs = CommerceNotification.objects.using('ecommerce').filter(pk__in=ids)
        if not (request.user.is_staff or request.user.is_superuser):
            qs = qs.filter(customer_id=request.user.pk)
        updated = qs.update(is_read=True)
        return Response({'updated': updated})

