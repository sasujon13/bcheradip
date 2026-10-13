from django import forms
from cheradip.models import WalletOperation
from .models import Order, Payment
from .order_service import TRANSITIONS


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
        if value in {'confirmed', 'refunded'} and current.method == 'wallet' and not WalletOperation.objects.filter(operation_key=f'commerce:debit:{current.order.number}').exists():
            raise forms.ValidationError('Reconcile the historical wallet payment first.')
        return value
