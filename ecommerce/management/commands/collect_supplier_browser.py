import getpass
import json
import sys
from django.core.management.base import BaseCommand, CommandError
from ecommerce.models import SupplierJob
from ecommerce.supplier_service import DB
from ecommerce.supplier_browser import BrowserCollector, SITES, start_job, CollectionStopped


class Command(BaseCommand):
    help = 'Read authorised supplier catalogues through normal Selenium sign-in/navigation. No orders, publication or cookie extraction.'

    def add_arguments(self, parser):
        parser.add_argument('--supplier', choices=[*SITES, 'all'], required=True)
        parser.add_argument('--username', default='01722710298')
        parser.add_argument('--headed', action='store_true')
        parser.add_argument('--max-pages', type=int, default=1000)
        parser.add_argument('--fill-missing-prices', action='store_true', help='Explicitly fill previously NULL source prices only; preserve all known prices and shop data.')
        parser.add_argument('--fill-missing-categories', action='store_true', help='Fill an absent source category only when the remaining identity/title agrees. Never replace a known category.')
        parser.add_argument('--start-page', type=int, default=1, help='Dropshipping catalogue only: resume via visible page links from a verified checkpoint.')
        parser.add_argument('--job-id')
        parser.add_argument('--input-json', action='store_true', help='Read a bounded one-run login from a private parent pipe; never store it.')
        parser.add_argument('--use-saved-credentials',action='store_true')
        parser.add_argument('--actor-id',type=int)
        parser.add_argument('--verify-visible',action='store_true',help='Verify visible catalogue/product buying prices and stock; do not create lightweight duplicate identities.')
        parser.add_argument('--skip', nargs='*', choices=list(SITES), default=[])

    def handle(self, *args, **opts):
        sites = list(SITES) if opts['supplier'] == 'all' else [opts['supplier']]
        sites = [site for site in sites if site not in opts['skip']]
        if opts['start_page'] != 1 and (sites != ['dropshipping'] or not 1 <= opts['start_page'] <= 10000):
            raise CommandError('A non-default start page is supported only for a single Dropshipping.com.bd catalogue.')
        if opts['start_page'] != 1 and opts['fill_missing_categories']:
            raise CommandError('Category enrichment starts each visible category at page one; it cannot use a combined-catalogue resume page.')
        self.stdout.write(('Using saved encrypted website sign-in; credentials are never logged.' if opts['use_saved_credentials'] else 'One-run password input is hidden and is not stored.')+' BDResellHUB remains on the owner waiting list.')
        if opts['input_json'] and opts['use_saved_credentials']:
            raise CommandError('Choose either saved credentials or one-run input.')
        if opts['use_saved_credentials']:
            username,password='',''
        elif opts['input_json']:
            try:
                data = json.loads(sys.stdin.readline(32768))
                username, password = data['username'], data['password']
                if not isinstance(username, str) or not isinstance(password, str) or len(username)>160 or len(password)>4096:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise CommandError('The one-run login input was invalid; no credential values were logged.') from None
        else:
            username = opts['username']
            password = getpass.getpass('Supplier login password: ')
        try:
            for site in sites:
                try:
                    if opts['use_saved_credentials']:
                        from ecommerce.models import Supplier
                        from ecommerce.supplier_crypto import decrypt
                        credentials=decrypt(Supplier.objects.using(DB).get(pk=SITES[site][0]))
                        username,password=credentials.get('username',''),credentials.get('password','')
                        credentials.clear()
                        if not username or not password:raise CollectionStopped('Normal website credentials are required for this browser collector; API keys are not a browser password.')
                    if opts['job_id']:
                        job = SupplierJob.objects.using(DB).select_related('supplier').get(pk=opts['job_id'],runner='browser',status='queued')
                        if job.payload.get('site') != site:
                            raise CommandError('Queued collector scope does not match this source.')
                        job.status='running'; job.save(using=DB,update_fields=['status','updated_at'])
                    else:
                        job = start_job(site,actor=opts['actor_id'])
                except CollectionStopped as exc:
                    self.stdout.write(f'{site}: {exc}')
                    continue
                self.stdout.write(f'{site} browser collection job: {job.pk}')
                collector=BrowserCollector
                if opts['verify_visible']:
                    from ecommerce.supplier_visible_catalogue import VisibleCatalogueCollector
                    collector=VisibleCatalogueCollector
                collector(site, job, username, password,
                    headless=not opts['headed'], max_pages=max(1, min(opts['max_pages'], 1000)),
                    fill_missing_prices=opts['fill_missing_prices'],fill_missing_categories=opts['fill_missing_categories'],start_page=opts['start_page']).run()
        finally:
            password = ''
