import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from ecommerce.supplier_service import run_jobs, nightly, cleanup


class Command(BaseCommand):
    help = 'Process bounded sourcing jobs, including configured read-only supplier APIs. No external purchases.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--scheduler', action='store_true', help='Designate this deployment for Dhaka nightly checks and log retention.')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            if options['scheduler']:
                nightly()
                cleanup()
            from ecommerce.catalog_sync_control import poll_requested_sync
            from ecommerce.upload_build import poll_requested_deploy
            poll_requested_sync()
            poll_requested_deploy()
            count = run_jobs(max_items=max(1, min(options['limit'], 1000)))
            if options['once']:
                self.stdout.write(f'Processed {count} sourcing items.')
                return
            time.sleep(2 if count else 5)
