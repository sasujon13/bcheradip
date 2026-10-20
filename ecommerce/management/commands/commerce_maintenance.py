"""Bounded, repeatable jobs for reservations, committed wallet operations and receipts."""
import logging
from django.conf import settings
from django.core.mail import send_mail, get_connection
from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.utils import timezone
from ecommerce.models import Order, CommerceNotification
from ecommerce.order_service import change_order
from cheradip.models import WalletOperation

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Expire unpaid reservations, reconcile committed wallet debits, and deliver private receipts.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=200)

    def handle(self, *args, **options):
        limit = max(1, min(options['limit'], 1000))
        expired = 0
        ids = list(Order.objects.using('ecommerce').filter(status='pending', payment_status='unpaid',
            reservation_expires_at__lte=timezone.now()).values_list('pk', flat=True)[:limit])
        for pk in ids:
            with transaction.atomic(using='ecommerce'):
                order = Order.objects.using('ecommerce').select_for_update().get(pk=pk)
                if order.status != 'pending' or order.payment_status != 'unpaid' or order.payments.exists():
                    continue
                if WalletOperation.objects.filter(operation_key=f'commerce:debit:{order.number}').exists():
                    continue
                change_order(pk, 'cancelled', note='Unpaid reservation expired; stock released. Please place a new order if still required.')
                expired += 1
        call_command('reconcile_commerce_wallets', apply=True, limit=limit, stdout=self.stdout)
        for pk in Order.objects.using('ecommerce').filter(receipt_pending=True, receipt_sent_at=None, receipt_attempts__lt=5).order_by('pk').values_list('pk', flat=True)[:min(limit, 10)]:
            with transaction.atomic(using='ecommerce'):
                order = Order.objects.using('ecommerce').select_for_update().get(pk=pk)
                if order.receipt_sent_at or order.receipt_attempts >= 5:
                    continue
                order.receipt_attempts += 1
                order.save(using='ecommerce', update_fields=['receipt_attempts', 'updated_at'])
                message = (f'Hello {order.customer_name},\nOrder ID: {order.number}\nProducts: BDT {order.subtotal}\nDiscount: BDT {order.discount_total}\n'
                    f'Delivery: BDT {order.shipping_total}\nCOD: BDT {order.cod_total}\nTotal: BDT {order.grand_total}\n'
                    f'Status: {order.get_status_display()}\nTrack at https://cheradip.com/ecommerce?view=track\n'
                    f'Private tracking token (do not share): {order.tracking_token}\n'
                    'Payments and fulfilment remain subject to administrative approval. This receipt does not confirm delivery.\n')
                try:
                    mail_options = {'timeout': getattr(settings, 'EMAIL_TIMEOUT', 15)}
                    sender = settings.DEFAULT_FROM_EMAIL
                    # The main site's transactional settings use SMTP_* (also edited
                    # in /admin/settings/), not Django's EMAIL_HOST_* names.
                    if settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend' and getattr(settings, 'SMTP_HOST', ''):
                        if not getattr(settings, 'SMTP_ENABLED', True):
                            raise RuntimeError('Transactional email is disabled by the administrator.')
                        mail_options.update(host=settings.SMTP_HOST, port=settings.SMTP_PORT,
                            username=settings.SMTP_USER, password=settings.SMTP_PASSWORD,
                            use_tls=settings.SMTP_USE_TLS, use_ssl=settings.SMTP_USE_SSL)
                        sender = settings.SMTP_FROM
                    sent = send_mail(f'Cheradip order receipt: {order.number}', message,
                                     sender, [order.email], fail_silently=False,
                                     connection=get_connection(**mail_options))
                    if not sent:
                        raise RuntimeError('Email backend did not accept the receipt.')
                    order.receipt_sent_at = timezone.now()
                    order.receipt_pending = False
                    order.save(using='ecommerce', update_fields=['receipt_sent_at', 'receipt_pending', 'updated_at'])
                except Exception:
                    logger.exception('Order receipt delivery failed for %s', order.number)
                    if order.receipt_attempts == 5:
                        CommerceNotification.objects.using('ecommerce').get_or_create(kind='system',
                            title=f'Receipt delivery failed: {order.number}', admin_only=True,
                            defaults={'message': 'Five receipt attempts failed. Check email configuration and contact the customer.',
                                      'link': f'/admin/ecommerce/order/{pk}/change/'})
        self.stdout.write(f'Expired unpaid reservations: {expired}')
