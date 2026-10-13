from django.core.management.base import BaseCommand
from cheradip.models import WalletOperation, WithdrawalRequest
from ecommerce.models import Order
from ecommerce.order_service import settle_wallet_order


class Command(BaseCommand):
    help = 'Inspect recoverable commerce payments. --apply only acknowledges already committed wallet debits/refunds; it never charges a user.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        for order in Order.objects.using('ecommerce').filter(payments__method='wallet').distinct().iterator():
            debit = WalletOperation.objects.filter(operation_key=f'commerce:debit:{order.number}').first()
            refund = WalletOperation.objects.filter(operation_key=f'commerce:refund:{order.number}').exists()
            if not debit:
                self.stdout.write(f'{order.number}: historical/unfunded order; manual reconciliation required. No balance changed.')
            elif debit.customer_id != order.customer_id or debit.coins != -int(order.grand_total * 100):
                self.stdout.write(f'{order.number}: ledger mismatch; manual investigation required.')
            elif order.payment_status != ('refunded' if refund else 'paid'):
                if options['apply']:
                    settle_wallet_order(order.pk)
                self.stdout.write(f'{order.number}: {"reconciled" if options["apply"] else "ready to reconcile"}.')
        count = WithdrawalRequest.objects.filter(reserved_coins=0, status__in=['pending', 'processing', 'approved']).count()
        self.stdout.write(f'Historical withdrawals without reservation: {count}. Review payment evidence; no automatic deductions are made.')
