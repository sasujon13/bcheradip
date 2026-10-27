"""Normal-source collection invoked by the staff workspace, using saved credentials."""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from ecommerce.models import SupplierRecollectionRun
from ecommerce.supplier_source_clients import SUPPLIER_IDS
from ecommerce.supplier_recollection import MAPPING_VERSION


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--supplier', choices=tuple(SUPPLIER_IDS), required=True)
        parser.add_argument('--actor-id',type=int)
        parser.add_argument('--source-mode',choices=('browser','structured'),default='browser',
            help='Browser-visible verification is preferred. Structured source traversal is explicit metadata enrichment only.')

    def handle(self, *args, **options):
        site = options['supplier']
        from pathlib import Path
        from django.conf import settings
        root = Path(settings.BASE_DIR) / 'private_suppliers' / 'recollection'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (root / (site + '.lock')).open('a+b') as lock:
            import os
            lock.seek(0)
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            try:
                import os
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.stdout.write('Full collection is already running; duplicate request ignored.')
                return
            if options['source_mode']=='browser':
                call_command('collect_supplier_browser',supplier=site,use_saved_credentials=True,verify_visible=True,
                    actor_id=options.get('actor_id'),
                    stdout=self.stdout,stderr=self.stderr)
            else:
                self.collect(site)

    def collect(self, site):
        supplier_id = SUPPLIER_IDS[site]
        from ecommerce.models import Supplier
        from ecommerce.supplier_crypto import decrypt
        public_only = False
        if site == 'selfshop':
            credentials = decrypt(Supplier.objects.using('ecommerce').get(pk=supplier_id))
            public_only = not bool(credentials.get('username') and credentials.get('password'))
            credentials.clear()
        common = {'supplier': site, 'use_saved_credentials': True, 'public_only': public_only,
                  'stdout': self.stdout, 'stderr': self.stderr, 'apply_missing_content': True}
        inspections = SupplierRecollectionRun.objects.using('ecommerce').filter(supplier_id=supplier_id,
                mode='inspect', mapping_version=MAPPING_VERSION, status='completed', processed__gte=3)
        if site == 'selfshop' and not public_only:
            inspections = inspections.filter(coverage__account_authenticated=True)
        if not inspections.exists():
            call_command('recollect_supplier_catalogue', mode='inspect', **common)
        previous = SupplierRecollectionRun.objects.using('ecommerce').filter(supplier_id=supplier_id,
            mode='full', mapping_version=MAPPING_VERSION, status__in=('paused', 'failed', 'completed_with_errors')).first()
        params = {**common, 'mode': 'full'}
        if previous and not previous.coverage.get('full_traversal'):
            params['run_id'] = str(previous.pk)
        call_command('recollect_supplier_catalogue', **params)
