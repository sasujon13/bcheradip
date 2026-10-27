"""Read-only inventory of full-source coverage, linkage and supplier access."""
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from django.core.management.base import BaseCommand
from django.utils import timezone
from ecommerce.models import Supplier, SupplierOffer, SupplierSourceProduct
from ecommerce.supplier_source_clients import SUPPLIER_IDS, SourceClient, SourceError


def product_url(value):
    parts = urlsplit(value or '')
    return urlunsplit(('https', (parts.hostname or '').removeprefix('www.'), parts.path.rstrip('/'), '', ''))


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--report', required=True)
        parser.add_argument('--check-access', action='store_true')

    def handle(self, *args, **options):
        sources = list(SupplierSourceProduct.objects.using('ecommerce').defer('raw_data', 'description'))
        url_index, id_index = defaultdict(list), defaultdict(list)
        for source in sources:
            url_index[source.supplier_id, product_url(source.url)].append(source)
            id_index[source.supplier_id, source.external_id].append(source)
        output = {'at': timezone.now().isoformat(), 'suppliers': [], 'link_candidates': []}
        for site, supplier_id in SUPPLIER_IDS.items():
            supplier = Supplier.objects.using('ecommerce').get(pk=supplier_id)
            offers = list(SupplierOffer.objects.using('ecommerce').filter(supplier=supplier))
            own_sources = [s for s in sources if s.supplier_id == supplier_id]
            fields = Counter()
            for source in own_sources:
                for key in source.quality.get('missing', []): fields[str(key)] += 1
            possible, ambiguous = 0, 0
            for offer in offers:
                if offer.source_product_id: continue
                candidates = url_index[supplier_id, product_url(offer.url)]
                if not candidates:
                    candidates = id_index[supplier_id, offer.external_id]
                if len(candidates) == 1:
                    source = candidates[0]
                    possible += 1
                    output['link_candidates'].append({'offer_id': offer.pk, 'source_id': source.pk,
                        'supplier': supplier_id, 'variant_id': offer.variant_id,
                        'url_equal': product_url(offer.url) == product_url(source.url),
                        'external_id_equal': offer.external_id == source.external_id})
                elif candidates: ambiguous += 1
            latest = supplier.recollections.filter(mode='full').values('id', 'status', 'processed', 'expected_total', 'activity').first()
            row = {'id': supplier.pk, 'name': supplier.name, 'enabled': supplier.enabled,
                'health': supplier.health, 'offers': len(offers), 'sources': len(own_sources),
                'unlinked': sum(not o.source_product_id for o in offers), 'link_candidates': possible,
                'ambiguous_links': ambiguous, 'availability': dict(Counter(o.availability for o in offers)),
                'source_stock_labels': dict(Counter(str(s.stock.get('status')) for s in own_sources)),
                'missing_source_fields': dict(fields), 'latest_full_run': latest}
            if options['check_access']:
                from ecommerce.supplier_crypto import decrypt
                credentials, client = {}, None
                try:
                    credentials = decrypt(supplier)
                    client = SourceClient(site, str(credentials.get('username') or ''), str(credentials.get('password') or ''),
                        public_only=site == 'selfshop')
                    client.login()
                    if site == 'resellkori':
                        import re
                        page = client.request(client.origin + '/products/')
                        restricted = bool(re.search(r'account (?:is )?(?:restricted|suspended|blocked)|অ্যাকাউন্ট.*(?:স্থগিত|ব্লক)', page.text, re.I))
                        row['access'] = 'supplier_account_restricted' if restricted else 'ordinary_signin_accepted'
                    else:
                        row['access'] = 'public_only_buying_price_unverified' if site == 'selfshop' else 'ordinary_signin_accepted'
                except (ValueError, SourceError):
                    row['access'] = 'normal_access_failed_reconnect_or_supplier_review_required'
                finally:
                    if client: client.close()
                    credentials.clear()
            output['suppliers'].append(row)
            self.stdout.write(json.dumps(row, default=str))
            self.stdout.flush()
        path = Path(options['report']).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, default=str, ensure_ascii=False), encoding='utf-8')
