"""Reconnect exact stored identities; preserve unknown fields and all order history."""
import json
from collections import Counter
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from ecommerce.models import SupplierSourceProduct, SupplierOffer
from ecommerce.supplier_recollection import apply_missing_content
from ecommerce.supplier_source_publish import source_variants, stock_observed_at


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--plan', required=True)
        parser.add_argument('--report', required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--after-source-id', type=int, default=0)
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        plan = json.loads(Path(options['plan']).read_text(encoding='utf-8'))
        ids = sorted({r['source_id'] for r in plan['link_candidates'] if r['source_id'] > options['after_source_id']})
        if options['limit']: ids = ids[:options['limit']]
        counts, failures, last = Counter(), [], options['after_source_id']
        output = Path(options['report'])
        output.parent.mkdir(parents=True, exist_ok=True)
        for source_id in ids:
            if options['apply']:
                source = SupplierSourceProduct.objects.using('ecommerce').get(pk=source_id)
                with transaction.atomic(using='ecommerce'):
                    counts.update(apply_missing_content(source_id, only_unlinked=True))
                    try: variants = source_variants(source)
                    except ValueError as exc:
                        variants = []
                        failures.append({'source_id':source_id, 'reason':str(exc)[:250]})
                    from django.db.models import Q
                    for offer in SupplierOffer.objects.using('ecommerce').select_for_update().filter(source_product_id=source_id).filter(Q(availability='unconfirmed')|Q(source_price=None)).exclude(state='excluded'):
                        matching = [v for v in variants if offer.variant_id in (v['id'], v['legacy_id']) or
                            (offer.variant_id.startswith('catalogue-type-') and not source.variants and not v['spec'])]
                        if len(matching) != 1: continue
                        row = matching[0]
                        if offer.observed_at and offer.observed_at > stock_observed_at(source): continue
                        offer.source_price = row['cost']
                        offer.quantity = row['quantity']
                        offer.availability = 'in_stock' if row['quantity'] or row.get('confirmation_required') else 'out_of_stock'
                        offer.observed_at = stock_observed_at(source)
                        offer.single_unit, offer.currency = True, 'BDT'
                        offer.save(using='ecommerce', update_fields=['source_price','quantity','availability','observed_at','single_unit','currency','updated_at'])
                        counts['price_stock_restored'] += 1
            last = source_id
            counts['sources_processed'] += 1
            if counts['sources_processed'] % 100 == 0:
                output.write_text(json.dumps({'counts':counts,'last_source_id':last,'failures':failures[-100:]}),encoding='utf-8')
                self.stdout.write(json.dumps({'counts':counts,'last_source_id':last}));self.stdout.flush()
        result = {'apply':options['apply'], 'counts':counts,'last_source_id':last,'failures':failures,
            'updated_at':timezone.now().isoformat()}
        output.write_text(json.dumps(result),encoding='utf-8')
        self.stdout.write(json.dumps({'counts':counts,'last_source_id':last,'unresolved_sources':len(failures)}))
