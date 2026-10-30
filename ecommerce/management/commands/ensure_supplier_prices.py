import json
from django.core.management.base import BaseCommand
from ecommerce.price_ensure import ensure_prices


class Command(BaseCommand):
    help = 'Check the eight current browser buying-price widgets against collected records. Never places orders.'

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true', help='Log in with saved credentials and re-read the eight product URLs.')

    def handle(self, *args, **options):
        from ecommerce.price_ensure import price_report_path
        try:
            result = ensure_prices()
            self.stdout.write(json.dumps({'status':result['status'],'rows':[
                {k:r.get(k) for k in ('site','live','collected','ok','error')} for r in result['rows']]},ensure_ascii=False))
        finally:
            price_report_path().with_suffix('.lock').unlink(missing_ok=True)
