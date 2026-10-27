"""Explicit owner-requested publication of complete, currently orderable observations."""
from collections import Counter
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError,connections
from django.utils import timezone
from ecommerce.models import SupplierRecollectionRun, Product
from ecommerce.supplier_source_publish import publish_source
from ecommerce.manual_catalogue import public_ids


class Command(BaseCommand):
    help = 'Publish verified original-photo, buying-price and stock observations. Never places orders.'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--archive-unverified', action='store_true')
        parser.add_argument('--completed-batch', action='store_true', help='Release individually complete observations while full traversal continues; never claims catalogue completion.')
        parser.add_argument('--after-source-id', type=int, default=0)
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--resume', action='store_true', help='Resume this finite release from its saved publication checkpoint; does not restart a completed release.')

    def handle(self, *args, **options):
        run = SupplierRecollectionRun.objects.using('ecommerce').get(pk=options['run_id'])
        finished = run.status in ('completed', 'completed_with_errors') and run.coverage.get('full_traversal')
        batch = options['completed_batch'] and run.status in ('running', 'paused', 'failed', 'completed', 'completed_with_errors')
        if run.mode != 'full' or not (finished or batch):
            raise CommandError('Use a completed full source traversal, not an inspection or interrupted catalogue.')
        if run.supplier_id not in (1,2,3,6,7,8,9):
            raise CommandError('This supplier still needs a verified price/stock publication adapter.')
        checkpoint=(run.coverage or {}).get('publication',{}) if options['resume'] else {}
        if checkpoint.get('status')=='completed':
            self.stdout.write(json.dumps({'run':str(run.pk),'publication':checkpoint,'already_completed':True}));return
        options['after_source_id']=max(options['after_source_id'],checkpoint.get('last_source_id',0))
        sources = run.products.order_by('pk')
        sources = sources.filter(pk__gt=options['after_source_id'])
        if options['limit'] > 0:
            sources = sources[:options['limit']]
        self.stdout.write(json.dumps({'run': str(run.pk), 'source_products': sources.count(),
            'complete_content': sum(not row.quality.get('missing') for row in sources.only('quality')), 'apply': options['apply'],
            'no_supplier_orders': True}))
        if not options['apply']:
            return
        counts, failures, last_source = Counter(), [], options['after_source_id']
        def save_checkpoint(state):
            if not options['resume']:return
            coverage=SupplierRecollectionRun.objects.using('ecommerce').get(pk=run.pk).coverage
            coverage['publication']={'status':state,'last_source_id':last_source,
                'counts_this_attempt':dict(counts),'updated_at':timezone.now().isoformat()}
            SupplierRecollectionRun.objects.using('ecommerce').filter(pk=run.pk).update(coverage=coverage,updated_at=timezone.now())
        from ecommerce.supplier_label_stock import SITES,read_stock,remember_stock,refresh_existing_offers,missing_stock
        from ecommerce.supplier_source_clients import SourceClient,SourceError
        from ecommerce.supplier_crypto import decrypt
        client=None;credentials={}
        save_checkpoint('running')
        try:
            if run.supplier_id in SITES:
                if not run.supplier.enabled or not run.supplier.terms_confirmed:
                    raise CommandError('Supplier access is paused; no requests attempted.')
                if run.supplier.credential_expires_at and run.supplier.credential_expires_at<=timezone.now():
                    raise CommandError('Supplier credentials expired; reconnect before release.')
                credentials=decrypt(run.supplier)
                client=SourceClient(SITES[run.supplier_id],credentials.get('username',''),credentials.get('password',''))
                client.login()
            for processed,source in enumerate(sources,1):
                try:
                    if client:
                        try:
                            data=read_stock(client,source)
                        except SourceError as exc:
                            if 'HTTP 404;' not in str(exc):raise
                            data=missing_stock(source)
                        checked=remember_stock(source,data)
                        refresh_existing_offers(source,data,checked)
                    counts.update(publish_source(source.pk))
                except SourceError:
                    raise  # Access/quota/network failure stops this batch, not thousands of retries.
                except (ValueError, OSError) as exc:
                    counts['held_sources'] += 1
                    failures.append({'source_id': source.external_id, 'reason': str(exc)[:300]})
                last_source = source.pk
                if processed % 25 == 0:
                    save_checkpoint('running')
                    self.stdout.write(json.dumps({'processed':processed,'counts':counts,'last_source_id':last_source}))
                    self.stdout.flush()
        except SourceError as exc:
            save_checkpoint('failed')
            raise CommandError(str(exc)+' Resume after the last logged checkpoint; successful writes remain idempotent.') from None
        except (CommandError,ValueError):
            save_checkpoint('failed')
            raise
        except DatabaseError:
            # A long read-only download may outlive a database connection.
            # Retry only from the idempotent saved cursor, not an uncertain
            # partially executed business write in this process.
            connections['ecommerce'].close()
            try:save_checkpoint('failed')
            except DatabaseError:pass  # The durable previous cursor remains.
            raise CommandError('Database connection interrupted. Successful catalogue writes are retained; resume the saved publication checkpoint after recovery.') from None
        finally:
            if client:client.close()
            credentials.clear()
        save_checkpoint('completed' if not run.products.filter(pk__gt=last_source).exists() else 'paused')
        archived = 0
        if options['archive_unverified']:
            # Status only. Keep original source records, images, orders, reviews,
            # customer data and all ordinary non-supplier products intact.
            archived = Product.objects.using('ecommerce').filter(
                supplier_offer__isnull=False, attributes__manual_supplier_catalogue=True, status='active'
            ).exclude(pk__in=public_ids()).update(status='archived', updated_at=timezone.now())
        self.stdout.write(json.dumps({'counts': counts, 'held_reasons': failures, 'last_source_id':last_source,
                                     'catalogue_traversal_complete':bool(finished), 'archived_unverified': archived,
                                     'public_supplier_products': len(list(public_ids()))}))
