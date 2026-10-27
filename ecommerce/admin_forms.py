from django import forms
from cheradip.models import WalletOperation
from .models import Order, Payment, Shipment, DeliverySettings, ProductVariant, Product
from .order_service import TRANSITIONS
from .pricing import COST_FIELDS, calculate_price, normalize_costs, normalize_default_costs
from .delivery_rates import listing_defaults, normalize_profiles


class ProductAdminForm(forms.ModelForm):
    color_mode = forms.ChoiceField(required=False, choices=[('', 'Use source; ambiguous colors remain mixed pending review'),
        ('mixed', 'Confirmed: one mixed-color design'), ('separate', 'Confirmed: separate selectable colors')])
    mixed_color_label = forms.CharField(required=False, max_length=200, help_text='For example: Pink & Blue')
    selectable_colors = forms.CharField(required=False, help_text='Confirmed separate choices, comma separated. Does not create supplier stock quantities.')

    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['secondary_categories'].queryset = self.fields['secondary_categories'].queryset.filter(
            is_active=True, parent__isnull=False, parent__parent__isnull=True)
        from .product_content import color_interpretation
        if self.instance.pk:
            policy = color_interpretation(self.instance)
            self.initial.update(color_mode=policy['mode'] if policy['mode'] in ('mixed', 'separate') else '',
                mixed_color_label=policy['label'], selectable_colors=', '.join(policy['choices']))

    def clean(self):
        data = super().clean()
        choices = list(dict.fromkeys(x.strip() for x in data.get('selectable_colors', '').split(',') if x.strip()))
        if data.get('color_mode') == 'separate' and not 2 <= len(choices) <= 20:
            self.add_error('selectable_colors', 'Enter between 2 and 20 verified color choices.')
        if data.get('color_mode') == 'mixed' and not data.get('mixed_color_label'):
            self.add_error('mixed_color_label', 'Enter the mixed-color name.')
        if 'attributes' in data:
            attrs = dict(data['attributes'] or {})
            marker = dict(attrs.get('_catalog', {}))
            if data.get('color_mode'):
                marker['color_decision'] = {'mode': data['color_mode'], 'label': data.get('mixed_color_label', ''), 'choices': choices}
            else:
                marker.pop('color_decision', None)
            attrs['_catalog'] = marker
            data['attributes'] = attrs
        return data


class ProductVariantAdminForm(forms.ModelForm):
    use_default_costs = forms.BooleanField(required=False, initial=True,
        label='Use central cost defaults and weight-derived courier budget', help_text='Only sourcing cost stays product-specific. Uncheck for manual per-item costs.')
    supplier_delivery_max = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, required=False, label='Maximum supplier delivery (Tk)')
    customer_delivery_charge = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, required=False, label='Customer delivery budget (Tk)')
    ads_cost = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, required=False, label='Ads cost per item (Tk)')
    packaging_cost = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, required=False, label='Packaging per item (Tk)')
    returns_allowance = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, required=False, label='Return / failed delivery allowance (Tk)')
    other_costs = forms.DecimalField(min_value=0, max_digits=14, decimal_places=2, required=False, label='Other costs per item (Tk)')
    apply_suggested_price = forms.BooleanField(required=False, label='Apply calculated selling price when saving',
        help_text='Opt-in only. All-cost markup: 20% through Tk100; 19% through Tk200; decrease one point per Tk100 to 10% above Tk1000.')

    class Meta:
        model = ProductVariant
        exclude = ('pricing_inputs',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].required = False
        policy = DeliverySettings.current()
        saved_costs = self.instance.pricing_inputs if isinstance(self.instance.pricing_inputs, dict) else {}
        try: defaults, _ = listing_defaults(policy, self.instance.weight_grams)
        except ValueError: defaults = {key:0 for key in COST_FIELDS}
        self.initial['use_default_costs'] = not saved_costs
        for key in COST_FIELDS:
            self.initial[key] = saved_costs.get(key, defaults[key])

    def clean(self):
        data = super().clean()
        if any(key in self.errors for key in COST_FIELDS):
            return data
        try:
            use_defaults = data.get('use_default_costs')
            costs = listing_defaults(DeliverySettings.current(),data.get('weight_grams',0))[0] if use_defaults else normalize_costs({key: data.get(key) if data.get(key) is not None else 0 for key in COST_FIELDS})
            if data.get('apply_suggested_price'):
                data['price'] = calculate_price(data.get('cost_price'), costs, subsidy_enabled=DeliverySettings.current().delivery_subsidy_enabled,rules=DeliverySettings.current().pricing_rules)['suggested_price']
            elif data.get('price') is None:
                self.add_error('price', 'Enter a selling price or select Apply calculated selling price.')
            self.instance.pricing_inputs = {} if use_defaults else costs
        except ValueError as exc:
            raise forms.ValidationError(str(exc))
        return data


class DeliverySettingsAdminForm(forms.ModelForm):
    def clean_pricing_rules(self):
        from .pricing import normalize_pricing_rules
        try:return normalize_pricing_rules(self.cleaned_data['pricing_rules'])
        except ValueError as exc:raise forms.ValidationError(str(exc))
    def clean_cost_defaults(self):
        try: return normalize_default_costs(self.cleaned_data['cost_defaults'])
        except ValueError as exc: raise forms.ValidationError(str(exc))

    def clean_courier_profiles(self):
        try: return normalize_profiles(self.cleaned_data['courier_profiles'])
        except ValueError as exc: raise forms.ValidationError(str(exc))
    dhaka_charge = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2)
    outside_dhaka_charge = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2)
    cod_percent = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2, label='Default COD charge (%)')
    unpaid_reservation_hours = forms.IntegerField(min_value=1, max_value=720)

    class Meta:
        model = DeliverySettings
        fields = '__all__'


class ShipmentAdminForm(forms.ModelForm):
    status = forms.ChoiceField(choices=[(s, s.title()) for s in ('preparing', 'shipped', 'delivered', 'returned')])

    class Meta:
        model = Shipment
        fields = '__all__'

    def clean(self):
        data = super().clean()
        order, status = data.get('order'), data.get('status')
        if self.instance.pk and order and self.instance.order_id != order.pk:
            self.add_error('order', 'A shipment cannot be moved to a different order.')
        if order and status and status != 'preparing' and status != order.status and status not in TRANSITIONS.get(order.status, set()):
            self.add_error('status', f'Cannot change a {order.status} order to {status}. Update the order through an allowed transition first.')
        return data


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'

    def clean_status(self):
        value = self.cleaned_data['status']
        if not self.instance.pk:
            return value
        current = Order.objects.using('ecommerce').get(pk=self.instance.pk)
        if value != current.status and value not in TRANSITIONS.get(current.status, set()):
            raise forms.ValidationError(f'Cannot change a {current.status} order to {value}.')
        if current.status=='pending' and value in {'confirmed','processing','shipped','delivered','completed'}:
            from .supplier_pilot import require_order_checks
            try: require_order_checks(current)
            except ValueError as exc: raise forms.ValidationError(str(exc))
        if value == 'completed':
            if current.payment_status == 'refunded':
                raise forms.ValidationError('This payment has been refunded.')
            if current.payments.filter(method='wallet').exists() and not WalletOperation.objects.filter(operation_key=f'commerce:debit:{current.number}').exists():
                raise forms.ValidationError('Reconcile the wallet payment before completing this order.')
        if value in {'cancelled', 'refunded'} and current.payments.filter(method='wallet').exists():
            if not WalletOperation.objects.filter(operation_key=f'commerce:debit:{current.number}').exists():
                raise forms.ValidationError('Historical wallet payment: manual reconciliation is required before refunding.')
        return value


class PaymentAdminForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = '__all__'

    def clean_status(self):
        value = self.cleaned_data['status']
        current = Payment.objects.using('ecommerce').select_related('order').get(pk=self.instance.pk)
        allowed = {'pending': {'confirmed', 'failed'}, 'confirmed': {'refunded'}, 'failed': set(), 'refunded': set()}
        if value != current.status and value not in allowed.get(current.status, set()):
            raise forms.ValidationError('Invalid payment status transition.')
        if value == 'confirmed' and current.order.status in {'cancelled', 'refunded'}:
            raise forms.ValidationError('This order is cancelled or refunded.')
        from .supplier_confirmation import pending as stock_pending
        if value == 'confirmed' and stock_pending(current.order):
            raise forms.ValidationError('Confirm supplier stock and delivery on the order first.')
        if value in {'confirmed', 'refunded'} and current.method == 'wallet' and not WalletOperation.objects.filter(operation_key=f'commerce:debit:{current.order.number}').exists():
            raise forms.ValidationError('Reconcile the historical wallet payment first.')
        return value
