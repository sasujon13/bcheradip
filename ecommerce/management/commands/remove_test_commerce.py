"""Explicit, narrowly scoped removal of a sample product and unpaid test history."""
from pathlib import Path
from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from cheradip.models import WalletOperation
from ecommerce.models import (Product, ProductVariant, ProductImage, Order, OrderItem,
    Payment, Shipment, OrderStatusHistory, InventoryMovement, CartItem, Review, CommerceNotification, SupplierOffer, SupplierSettlementEntry)


class Command(BaseCommand):
    help = 'Remove explicitly identified test data, with a private recovery backup. Refuses payment/wallet history or unrelated orders.'

    def add_arguments(self, parser):
        parser.add_argument('--product-id', required=True, type=int)
        parser.add_argument('--order-id', required=True, type=int)
        parser.add_argument('--confirm-test-data', action='store_true')

    @transaction.atomic(using='ecommerce')
    def handle(self, *args, **options):
        if not options['confirm_test_data']:
            raise CommandError('Explicit --confirm-test-data is required.')
        product = Product.objects.using('ecommerce').select_for_update().get(pk=options['product_id'])
        order = Order.objects.using('ecommerce').select_for_update().get(pk=options['order_id'])
        variants = ProductVariant.objects.using('ecommerce').select_for_update().filter(product=product)
        if not variants.exists() or any(not sku.startswith('SAMPLE-') for sku in variants.values_list('sku', flat=True)):
            raise CommandError('Not an identified sample product. Nothing removed.')
        items = order.items.all()
        if not items.exists() or items.exclude(product_id=product.pk).exists() or OrderItem.objects.using('ecommerce').filter(product_id=product.pk).exclude(order=order).exists():
            raise CommandError('Contains unrelated order history. Nothing removed.')
        if order.payments.exists() or order.shipments.exists() or order.coupon_code or SupplierOffer.objects.using('ecommerce').filter(imported_product=product).exists() or SupplierSettlementEntry.objects.using('ecommerce').filter(order=order).exists():
            raise CommandError('Payment, shipment, coupon or supplier links require manual review. Nothing removed.')
        if WalletOperation.objects.filter(operation_key__in=[f'commerce:debit:{order.number}', f'commerce:refund:{order.number}']).exists():
            raise CommandError('Wallet ledger links exist. Nothing removed.')
        notifications = CommerceNotification.objects.using('ecommerce').filter(Q(link=f'/history?order={order.number}') | Q(link=f'/history?order={order.number}&from=ecommerce'))
        objects = [product, *variants, *ProductImage.objects.using('ecommerce').filter(product=product),
                   *Review.objects.using('ecommerce').filter(product=product),
                   *InventoryMovement.objects.using('ecommerce').filter(variant__in=variants),
                   *CartItem.objects.using('ecommerce').filter(variant__in=variants), order,
                   *items, *order.history.all(), *notifications]
        folder = Path(settings.BASE_DIR) / 'private_suppliers' / 'recovery'
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f'test-product-{product.pk}-order-{order.pk}-{timezone.now():%Y%m%d%H%M%S%f}.json'
        with backup.open('x', encoding='utf-8') as stream:
            serializers.serialize('json', objects, stream=stream)
        notifications.delete()
        order.delete(using='ecommerce')
        product.delete(using='ecommerce')
        self.stdout.write(self.style.SUCCESS(f'Removed test product and test order. No wallet changes. Recovery backup: {backup}'))
