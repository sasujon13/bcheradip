from decimal import Decimal

from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from cheradip.views import BearerTokenAuthentication
from .models import Cart, DeliverySettings, Payment
from .checkout_rules import AddressSerializer, quote_totals
from .permissions import IsCommerceAdmin
from .throttles import TrackingThrottle
from .views import CommerceAdminAuthMixin
from .delivery_rates import normalize_profiles
from .pricing import normalize_default_costs


class DeliverySettingsSerializer(serializers.ModelSerializer):
    def validate_pricing_rules(self,value):
        from .pricing import normalize_pricing_rules
        try:return normalize_pricing_rules(value)
        except ValueError as exc:raise serializers.ValidationError(str(exc))
    def validate_cost_defaults(self, value):
        try: return normalize_default_costs(value)
        except ValueError as exc: raise serializers.ValidationError(str(exc))

    def validate_courier_profiles(self, value):
        try: return normalize_profiles(value)
        except ValueError as exc: raise serializers.ValidationError(str(exc))
    dhaka_charge = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    outside_dhaka_charge = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    cod_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    unpaid_reservation_hours = serializers.IntegerField(min_value=1, max_value=720)

    class Meta:
        model = DeliverySettings
        fields = ('id', 'dhaka_charge', 'outside_dhaka_charge', 'cod_percent', 'delivery_subsidy_enabled', 'unpaid_reservation_hours', 'return_policy', 'support_phone', 'cost_defaults', 'courier_profiles','pricing_rules')
        read_only_fields = ('id',)


class StorePolicyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        data = DeliverySettingsSerializer(DeliverySettings.current()).data
        data.pop('unpaid_reservation_hours', None)
        data.pop('cost_defaults', None); data.pop('courier_profiles', None)
        data.pop('delivery_subsidy_enabled', None)
        data.pop('pricing_rules',None)
        data['delivery_calculation'] = 'weight_range_midpoint'
        return Response(data)


class DeliverySettingsView(CommerceAdminAuthMixin, APIView):
    permission_classes = [IsCommerceAdmin]
    permission_model = DeliverySettings

    def get(self, request):
        return Response(DeliverySettingsSerializer(DeliverySettings.current()).data)

    def patch(self, request):
        from django.db import transaction
        with transaction.atomic(using='ecommerce'):
            DeliverySettings.objects.using('ecommerce').get_or_create(pk=1)
            config=DeliverySettings.objects.using('ecommerce').select_for_update().get(pk=1)
            serializer = DeliverySettingsSerializer(config, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            if 'pricing_rules' in serializer.validated_data:
                from .supplier_service import policy,audit
                current=policy();current.revision+=1;current.save(using='ecommerce',update_fields=['revision','updated_at'])
                audit('central_pricing_rules_saved',request.user.pk,rules=config.pricing_rules,existing_orders_unchanged=True)
        return Response(serializer.data)


class CheckoutProfileView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        from .phone_display import local_contact
        return Response({'customer_name': user.fullName, 'email': user.email or '',
            'phone': local_contact(user.username,user.country_code or 'BD'), 'phone_alternate': local_contact(user.phone_alternate,user.country_code or 'BD'),
            'country_code': user.country_code or 'BD', 'division': user.division,
            'district': user.district, 'thana': user.thana, 'zone': user.union, 'address': user.village})


class CheckoutQuoteView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [TrackingThrottle]

    def post(self, request):
        cart = Cart.objects.using('ecommerce').filter(token=request.data.get('cart_token'), checked_out=False).first()
        user_id = request.user.pk if request.user.is_authenticated else None
        if not cart or (cart.customer_id and cart.customer_id != user_id):
            return Response({'detail': 'Cart is unavailable for this account.'}, status=404)
        address = AddressSerializer(data=request.data.get('shipping_address', {}))
        address.is_valid(raise_exception=True)
        items = list(cart.items.select_related('variant__product'))
        if not items:
            return Response({'detail': 'Your cart is empty.'}, status=400)
        from .supplier_guards import is_supplier_staging, MESSAGE
        if any(is_supplier_staging(item.variant.product_id) for item in items):
            return Response({'detail': MESSAGE}, status=409)
        if any(not i.variant.is_active or i.variant.product.status != 'active' or
               (not i.variant.allow_backorder and i.quantity > i.variant.stock) for i in items):
            return Response({'detail': 'A cart item is unavailable or has insufficient stock.'}, status=409)
        subtotal = sum((i.variant.price * i.quantity for i in items), Decimal('0'))
        method = serializers.ChoiceField(choices=Payment.METHODS).run_validation(request.data.get('payment_method', 'cod'))
        from .supplier_confirmation import checkout_policy
        try:
            confirmation=checkout_policy([(i.variant,i.quantity) for i in items],method)
        except ValueError as exc:
            return Response({'detail':str(exc)},status=409)
        totals, _ = quote_totals(subtotal, any(i.variant.requires_shipping for i in items),
                                 address.validated_data, str(request.data.get('coupon_code') or ''),
                                 lines=[(i.variant, i.quantity) for i in items], payment_method=method)
        from .supplier_pilot import validate_checkout
        try:
            validate_checkout([(i.variant,i.quantity) for i in items],totals)
        except ValueError as exc:
            return Response({'detail':str(exc)},status=409)
        totals.update(stock_confirmation_required=confirmation['required'],confirmation_notice=confirmation['notice'],
                      quantity_unspecified=confirmation['quantity_unspecified'],order_auto_confirmed=confirmation['auto_confirmed'])
        return Response(totals)
