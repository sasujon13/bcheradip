import json
from django.core.management.base import BaseCommand
from ecommerce.price_ensure import ensure_prices


class Command(BaseCommand):
    help = 'Check owner gold HTML buying prices; optional live sign-in fetch. Never places supplier orders.'

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true', help='Log in with saved credentials and re-read the eight product URLs.')

    def handle(self, *args, **options):
        result = ensure_prices(live=options['live'])
        self.stdout.write(json.dumps({
            'gold_ok': result['gold_ok'],
            'gold': [{'site': r['site'], 'expected': r['expected'], 'extracted': r['extracted'], 'ok': r['ok']} for r in result['rows']],
            'live': None if not result['live'] else {
                'ok': result['live']['ok'],
                'rows': [{'site': r['site'], 'expected': r['expected'], 'live': r['live'], 'ok': r['ok'],
                          'error': r['error']} for r in result['live']['rows']],
            },
        }, ensure_ascii=False))
