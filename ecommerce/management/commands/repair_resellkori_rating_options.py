"""Remove WooCommerce review ratings accidentally collected as product options."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from ecommerce.models import SupplierSourceProduct


class Command(BaseCommand):
    help = 'Preview or remove ResellKori review-rating controls from source variants.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--republish-verified', action='store_true')

    def handle(self, *args, **options):
        if options['republish_verified'] and not options['apply']:
            self.stderr.write('--republish-verified requires --apply.')
            return
        changed = published = held = 0
        from ecommerce.supplier_source_publish import publish_source
        sources = SupplierSourceProduct.objects.using('ecommerce').filter(supplier_id=8).iterator(chunk_size=200)
        for source in sources:
            current = source.variants if isinstance(source.variants, list) else []
            remaining = [option for option in current if not (
                isinstance(option, dict) and str(option.get('name') or '').casefold() == 'rating')]
            if len(remaining) == len(current):
                continue
            changed += 1
            if not options['apply']:
                continue
            SupplierSourceProduct.objects.using('ecommerce').filter(pk=source.pk).update(
                variants=remaining, updated_at=timezone.now())
            proof=(source.extra or {}).get('browser_verification') or {}
            if options['republish_verified'] and proof.get('state') == 'verified':
                try:
                    publish_source(source.pk)
                    published += 1
                except (ValueError, OSError):
                    held += 1
        self.stdout.write(f'Rating controls removed from {changed} source products; '
                          f'publication attempted {published + held}, succeeded {published}, held {held}.')
        self.stdout.write('Applied.' if options['apply'] else 'Preview only.')
