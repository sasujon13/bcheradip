from django.core.management.base import BaseCommand
from cheradip.models import WalletOperation, WithdrawalRequest
from ecommerce.models import Order, CommerceNotification
from ecommerce.order_service import settle_wallet_order


class Command(BaseCommand):
    help = 'Inspect recoverable commerce payments. --apply only acknowledges already committed wallet debits/refunds; it never charges a user.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--limit', type=int, default=1000)

    def handle(self, *args, **options):
        pending = Order.objects.using('ecommerce').filter(payments__method='wallet').exclude(payment_status__in=['paid', 'refunded']).distinct().order_by('updated_at', 'pk')[:max(1, min(options['limit'], 5000))]
        for order in pending:
            debit = WalletOperation.objects.filter(operation_key=f'commerce:debit:{order.number}').first()
            refund = WalletOperation.objects.filter(operation_key=f'commerce:refund:{order.number}').exists()
            if not debit:
                self.stdout.write(f'{order.number}: historical/unfunded order; manual reconciliation required. No balance changed.')
                if options['apply']:
                    self.alert(order)
            elif debit.customer_id != order.customer_id or debit.coins != -int(order.grand_total * 100):
                self.stdout.write(f'{order.number}: ledger mismatch; manual investigation required.')
                if options['apply']:
                    self.alert(order)
            elif order.payment_status != ('refunded' if refund else 'paid'):
                if options['apply']:
                    settle_wallet_order(order.pk)
                self.stdout.write(f'{order.number}: {"reconciled" if options["apply"] else "ready to reconcile"}.')
        count = WithdrawalRequest.objects.filter(reserved_coins=0, status__in=['pending', 'processing', 'approved']).count()
        self.stdout.write(f'Historical withdrawals without reservation: {count}. Review payment evidence; no automatic deductions are made.')

    def alert(self, order):
        CommerceNotification.objects.using('ecommerce').get_or_create(kind='system',
            title=f'Wallet reconciliation needs review: {order.number}', admin_only=True,
            defaults={'message': 'Missing or mismatched committed debit. No additional charge was made.',
                      'link': f'/admin/ecommerce/order/{order.pk}/change/'})
