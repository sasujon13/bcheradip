"""Restore only auto-archived supplier listings still eligible under current rules."""
from django.core.management.base import BaseCommand
from django.db import transaction

from ecommerce.manual_catalogue import purchasable_offers
from ecommerce.models import Product


class Command(BaseCommand):
    help = 'Restore listings archived solely by an expired source check; never restore staff archives or out-of-stock items.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        candidates = Product.objects.using('ecommerce').filter(
            status='archived', attributes__source_stock_hold=True,
            pk__in=purchasable_offers().values('imported_product_id'),
        ).values_list('pk', flat=True)
        ids = list(candidates)
        if not options['dry_run']:
            for product_id in ids:
                with transaction.atomic(using='ecommerce'):
                    product = Product.objects.using('ecommerce').select_for_update().get(pk=product_id)
                    if product.status != 'archived' or not product.attributes.get('source_stock_hold'):
                        continue
                    if not purchasable_offers().filter(imported_product_id=product_id).exists():
                        continue
                    product.attributes = {**product.attributes, 'source_stock_hold': False}
                    product.status = 'active'
                    product.save(using='ecommerce', update_fields=['status', 'attributes', 'updated_at'])
        self.stdout.write(f'{len(ids)} source-held listings {"eligible" if options["dry_run"] else "restored"}.')
