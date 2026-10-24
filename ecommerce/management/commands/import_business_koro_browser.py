import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from ecommerce.models import Supplier
from ecommerce.business_koro_catalogue import import_catalogue


class Command(BaseCommand):
    help = 'Reconcile permitted visible Business Koro reseller cards; never publishes or submits orders.'

    def add_arguments(self, parser):
        parser.add_argument('snapshot', type=Path)

    def handle(self, *args, **opts):
        path = opts['snapshot'].resolve(strict=True)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise CommandError('Use a browser card snapshot up to 2 MB.')
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            supplier = Supplier.objects.using('ecommerce').get(connector='business_koro')
            result = import_catalogue(supplier, payload['cards'])
        except (ValueError, KeyError, Supplier.DoesNotExist, Supplier.MultipleObjectsReturned):
            raise CommandError('Invalid browser snapshot or supplier configuration.') from None
        self.stdout.write(json.dumps(result, ensure_ascii=False))
