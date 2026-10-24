"""Explicit owner action; not part of deployment or the nightly scheduler."""
from django.core.management.base import BaseCommand, CommandError
from ecommerce.models import SupplierPolicy, Product
from ecommerce.manual_catalogue import queue_imports, eligible_offers
from ecommerce.supplier_service import policy, run_jobs


class Command(BaseCommand):
    help = 'Keep All collected supplier listings live for manual fulfilment, or Keep Filtered research-approved listings only.'

    def add_arguments(self, parser):
        parser.add_argument('--mode', choices=['all', 'filtered'], required=True)
        parser.add_argument('--confirm-manual-fulfilment', action='store_true')
        parser.add_argument('--run', action='store_true')

    def handle(self, *args, **options):
        if not options['confirm_manual_fulfilment']:
            raise CommandError('Explicit --confirm-manual-fulfilment is required. This does not authorise supplier purchases.')
        config = policy()
        config.catalogue_mode = options['mode']; config.catalogue_revision += 1
        config.save(using='ecommerce', update_fields=['catalogue_mode','catalogue_revision','updated_at'])
        ids = eligible_offers().exclude(imported_product=None).values('imported_product_id')
        linked = Product.objects.using('ecommerce').filter(supplier_offer__isnull=False)
        archived = linked.exclude(pk__in=ids).update(status='archived')
        restored = linked.filter(pk__in=ids).update(status='active')
        jobs = queue_imports() if options['mode']=='all' else []
        self.stdout.write(f'Mode {options["mode"]}; restored {restored}; archived {archived}; import jobs {len(jobs)}', ending='\n')
        if options['run']:
            while True:
                n = run_jobs(max_items=500)
                self.stdout.write(f'Processed {n}; live supplier products {linked.filter(status="active").count()}')
                self.stdout.flush()
                if n == 0: break
