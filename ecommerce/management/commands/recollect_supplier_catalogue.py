"""Fresh catalogue staging; all writes are limited to source data and optional missing content."""
import json
import sys
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction,DatabaseError,connections
from django.utils import timezone
from ecommerce.models import Supplier, SupplierRecollectionRun, SupplierRecollectionItem
from ecommerce.supplier_recollection import save_record, save_failure, source_key, apply_missing_content,MAPPING_VERSION
from ecommerce.supplier_source_clients import SourceClient, SourceError, SUPPLIER_IDS


class Command(BaseCommand):
    help = 'Inspect or freshly recollect original supplier data, with persisted progress and safe resume.'

    def add_arguments(self, parser):
        parser.add_argument('--supplier', choices=list(SUPPLIER_IDS))
        parser.add_argument('--mode', choices=['inspect', 'full'], default='inspect')
        parser.add_argument('--run-id')
        parser.add_argument('--status', action='store_true')
        parser.add_argument('--input-json', action='store_true', help='Read one-run login JSON from stdin; never saved.')
        parser.add_argument('--max-products', type=int, default=0, help='Pause after this many new observations; zero means the full source.')
        parser.add_argument('--apply-missing-content', action='store_true', help='Fill empty descriptions/add actual source images on exactly linked old listings. Never change prices.')
        parser.add_argument('--public-only', action='store_true', help='Explicitly collect public product content; gated buying prices remain unverified.')
        parser.add_argument('--use-saved-credentials',action='store_true',help='Use the authorised encrypted supplier account login; never prints or exports credentials.')

    def handle(self, *args, **options):
        if options['status']:
            rows = SupplierRecollectionRun.objects.using('ecommerce').select_related('supplier').order_by('-created_at')[:24]
            self.stdout.write(json.dumps([{'run_id': str(r.pk), 'supplier': r.supplier.name, 'mode': r.mode,
                'status': r.status, 'processed': r.processed, 'expected': r.expected_total, 'counts': r.counts,
                'activity': r.activity, 'last_update': r.updated_at.isoformat()} for r in rows], indent=2))
            return
        if options['max_products'] < 0:
            raise CommandError('max-products cannot be negative.')
        credentials = {}
        if options['input_json']:
            try:
                credentials = json.load(sys.stdin)
            except (ValueError, TypeError):
                raise CommandError('Invalid one-run login JSON; no credentials were saved.') from None
            if not isinstance(credentials, dict):
                raise CommandError('One-run login must be a JSON object.')
        site = options['supplier']
        if not site:
            raise CommandError('Select an inspected supplier.')
        supplier_id = SUPPLIER_IDS[site]
        if options['use_saved_credentials']:
            if options['input_json']:raise CommandError('Choose saved credentials or one-run input, not both.')
            from ecommerce.supplier_crypto import decrypt
            supplier=Supplier.objects.using('ecommerce').get(pk=supplier_id)
            if not supplier.enabled or not supplier.terms_confirmed:raise CommandError('Supplier access is paused; no login attempted.')
            if supplier.credential_expires_at and supplier.credential_expires_at<=timezone.now():
                raise CommandError('Saved supplier credentials expired; reconnect before recollecting.')
            if not options['public_only']:
                credentials=decrypt(supplier)
        with transaction.atomic(using='ecommerce'):
            supplier = Supplier.objects.using('ecommerce').select_for_update().get(pk=supplier_id)
            if not supplier.enabled or not supplier.terms_confirmed:
                raise CommandError('Supplier must be enabled with documented authorised access.')
            if options['run_id']:
                run = SupplierRecollectionRun.objects.using('ecommerce').select_for_update().get(pk=options['run_id'], supplier=supplier)
                if run.status not in ('paused', 'failed', 'completed_with_errors'):
                    raise CommandError('Only paused/failed/incomplete runs may be resumed. A running run must not overlap.')
            else:
                if SupplierRecollectionRun.objects.using('ecommerce').filter(supplier=supplier, status__in=('running', 'queued', 'cancel_requested')).exists():
                    raise CommandError('This supplier already has an active recollection.')
                if supplier.recollections.filter(coverage__publication__status='running').exists():
                    raise CommandError('Complete or resume the current verified release before rewriting its source observations.')
                if options['mode'] == 'full' and not SupplierRecollectionRun.objects.using('ecommerce').filter(
                        supplier=supplier, mode='inspect', status='completed', processed__gte=3,mapping_version=MAPPING_VERSION).exists():
                    raise CommandError('Complete at least three fresh source inspections with this mapper before a full run.')
                run = SupplierRecollectionRun.objects.using('ecommerce').create(supplier=supplier, mode=options['mode'],mapping_version=MAPPING_VERSION)
            run.status = 'running'
            run.started_at = run.started_at or timezone.now()
            run.finished_at = None
            run.activity = 'Connecting to original supplier sources; no legacy-record fallback'
            run.save(using='ecommerce')
        self.stdout.write(f'Run {run.pk}: {supplier.name} — {run.mode}')
        self.stdout.flush()
        last_progress = [0]
        def progress(**fields):
            current = SupplierRecollectionRun.objects.using('ecommerce').get(pk=run.pk)
            if current.status == 'cancel_requested':
                raise SourceError('Cancellation requested; saved source records are retained.')
            if current.status != 'running':
                raise SourceError('Source run is no longer active.')
            if time.monotonic() - last_progress[0] >= 5:
                SupplierRecollectionRun.objects.using('ecommerce').filter(pk=run.pk).update(**fields, updated_at=timezone.now())
                last_progress[0] = time.monotonic()
        skip_ids = set(run.items.filter(status__in=('complete', 'incomplete')).values_list('external_id', flat=True))
        client = SourceClient(site, str(credentials.get('username') or ''), str(credentials.get('password') or ''), progress,
                              skip_ids=skip_ids, public_only=options['public_only'])
        done = 0
        try:
            for record in client.products():
                if record.get('_error'):
                    save_failure(run.pk, record)
                    done += 1
                    run.refresh_from_db(using='ecommerce')
                    if run.mode == 'inspect' and run.processed >= 3:
                        run.status = 'completed_with_errors'
                        run.coverage = {**client.coverage, 'sample_only': True, 'full_traversal': False}
                        break
                    if options['max_products'] and done >= options['max_products']:
                        run.refresh_from_db(using='ecommerce'); run.status = 'paused'
                        run.coverage = {**client.coverage, 'full_traversal': False}
                        break
                    continue
                # Same-run checkpoints skip writes, not fresh discovery. Never seed a new run from old incomplete offers.
                key = source_key(record['external_id'], record.get('vendor_id', ''), record.get('warehouse_id', ''))
                if SupplierRecollectionItem.objects.using('ecommerce').filter(run=run, source_key=key, status__in=('complete', 'incomplete')).exists():
                    continue
                outcome = save_record(run.pk, record)
                done += 1
                run.refresh_from_db(using='ecommerce')
                if options['apply_missing_content'] and outcome == 'complete':
                    item = run.items.get(source_key=key)
                    changes = apply_missing_content(item.source_product_id)
                    self.stdout.write(json.dumps({'processed': run.processed, 'content_changes': changes}))
                elif done == 1 or done % 10 == 0:
                    self.stdout.write(f'{supplier.name}: {run.processed} saved — {run.counts}')
                self.stdout.flush()
                if run.mode == 'inspect' and run.processed >= 3:
                    run.status = 'completed' if run.counts.get('complete', 0) >= 3 else 'completed_with_errors'
                    run.coverage = {**client.coverage, 'sample_only': True, 'full_traversal': False}
                    break
                if options['max_products'] and done >= options['max_products']:
                    run.status = 'paused'
                    run.coverage = {**client.coverage, 'full_traversal': False}
                    break
            else:
                run.refresh_from_db(using='ecommerce')
                run.status = 'completed_with_errors' if run.counts.get('incomplete') or run.counts.get('failed') or client.coverage['access_gaps'] else 'completed'
                run.coverage = {**client.coverage, 'full_traversal': True}
                if run.mode=='full':
                    from ecommerce.supplier_source_publish import refresh_listing_stock
                    from ecommerce.models import SupplierOffer
                    absent=supplier.source_products.exclude(last_run=run).exclude(extra__pending_identity_review__isnull=False)
                    missing_ids=[]
                    for source in absent.iterator():
                        # Catalogue absence is not a new price/quantity confirmation.
                        source.stock={**source.stock,'status':'missing'}
                        source.extra={**source.extra,'not_seen_in_catalogue':{'run_id':str(run.pk),'checked_at':timezone.now().isoformat()}}
                        source.save(using='ecommerce',update_fields=['stock','extra','updated_at']);missing_ids.append(source.pk)
                    run.coverage['not_seen_in_current_catalogue']=len(missing_ids)
                    for offer in SupplierOffer.objects.using('ecommerce').filter(source_product_id__in=missing_ids):
                        with transaction.atomic(using='ecommerce'):
                            offer=SupplierOffer.objects.using('ecommerce').select_for_update().get(pk=offer.pk)
                            offer.availability='missing';offer.save(using='ecommerce',update_fields=['availability','updated_at'])
                            if offer.source_price is not None and offer.source_price>0:
                                refresh_listing_stock(offer)
            run.expected_total = client.expected_total
            run.finished_at = timezone.now() if run.status != 'paused' else None
            run.activity = f'{run.status}: {run.processed} original-source products saved; missing content and access gaps are recorded'
            run.save(using='ecommerce')
        except DatabaseError:
            connections['ecommerce'].close()
            try:
                run.refresh_from_db(using='ecommerce')
                run.status='paused'
                run.activity='Database connection interrupted; resume this run after recovery. Original observations are retained.'
                run.save(using='ecommerce',update_fields=['status','activity','updated_at'])
            except DatabaseError:pass
            raise CommandError(f'Run {run.pk}: database connection interrupted; saved source observations are retained. Resume after recovery.') from None
        except (SourceError, ValueError, KeyError, TypeError) as exc:
            run.refresh_from_db(using='ecommerce')
            run.status = 'cancelled' if run.status == 'cancel_requested' else 'failed'
            # Unexpected source schemas/errors never print raw responses, payloads, tokens or requests.
            message = str(exc) if isinstance(exc, SourceError) else f'{type(exc).__name__}: source mapper or record validation requires review'
            run.errors = (run.errors + [{'message': message[:500], 'at': timezone.now().isoformat()}])[-100:]
            run.coverage = {**client.coverage, 'full_traversal': False}
            run.expected_total = client.expected_total
            run.activity = message[:500]
            run.finished_at = timezone.now()
            run.save(using='ecommerce')
            raise CommandError(f'Run {run.pk}: {message}. Saved checkpoints are retained.') from None
        finally:
            client.close()
            credentials.clear()
        self.stdout.write(json.dumps({'run_id': str(run.pk), 'status': run.status, 'processed': run.processed,
            'expected_total': run.expected_total, 'counts': run.counts, 'coverage': run.coverage}, ensure_ascii=False))
