"""Incremental original-source observations only. No customers, orders or credentials."""
from pathlib import Path
import gzip
import json
import os
import hashlib
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from ecommerce.models import Supplier, SupplierRecollectionRun, SupplierSourceProduct, SupplierSourceMedia
from ecommerce.supplier_recollection import validate_record

FIELDS = ('external_id', 'vendor_id', 'warehouse_id', 'url', 'title', 'sku', 'short_description', 'description',
          'categories', 'specifications', 'features', 'prices', 'stock', 'variants', 'shipping', 'extra', 'raw_data')


class Command(BaseCommand):
    help = 'Transfer one verified full-source run incrementally, never business identities or orders.'

    def add_arguments(self, parser):
        parser.add_argument('--run-id')
        parser.add_argument('--export', dest='export_path')
        parser.add_argument('--import', dest='import_path')
        parser.add_argument('--export-directory')
        parser.add_argument('--import-directory')

    def handle(self, *args, **options):
        if sum(bool(options.get(k)) for k in ('export_path','import_path','export_directory','import_directory')) != 1:
            raise CommandError('Select one export/import file or directory.')
        if options.get('export_directory'):
            return self.export_directory(options['run_id'], options['export_directory'])
        if options.get('import_directory'):
            root = Path(options['import_directory']).resolve()
            manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
            if manifest.get('format') != 'cheradip-source-parts-v1' or not isinstance(manifest.get('parts'),list):
                raise CommandError('Invalid bounded source manifest.')
            for part in manifest['parts']:
                name = part.get('file','')
                if not name.endswith('.json.gz') or '/' in name or '\\' in name or name != Path(name).name:
                    raise CommandError('Invalid source part name.')
                path = (root/name).resolve()
                if path.parent != root or path.stat().st_size > 64*1024*1024:
                    raise CommandError('Source part escapes its directory or exceeds the limit.')
                with path.open('rb') as stream:
                    actual = hashlib.file_digest(stream,'sha256').hexdigest()
                if actual != part.get('sha256'):
                    raise CommandError('Source part checksum differs; import stopped without touching unrelated records.')
                self.import_file(path)
            return
        if options['export_path']:
            run = SupplierRecollectionRun.objects.select_related('supplier').get(pk=options['run_id'])
            if run.products.count() > 100:
                raise CommandError('Use --export-directory for more than 100 source products; large all-in-memory transfers are disabled.')
            rows = []
            for product in run.products.order_by('pk'):
                media = [{'url': m.original_url, 'kind': m.kind, 'role': m.role, 'variant_id': m.variant_id,
                          'alt': m.alt_text, 'metadata': {k: v for k, v in m.metadata.items() if k not in
                              ('verified_image', 'cached_name', 'sha256', 'width', 'height','verified_run_id','verified_at')}}
                         for m in product.media.filter(last_run=run)]
                rows.append({**{f: getattr(product, f) for f in FIELDS}, 'media': media,
                             'observed_at': product.observed_at.isoformat()})
            payload = {'format': 'cheradip-original-source-v1', 'run_id': str(run.pk),
                'supplier': {'id': run.supplier_id, 'website': run.supplier.website},
                'mode': run.mode, 'status': run.status, 'coverage': run.coverage, 'counts': run.counts,
                'expected_total': run.expected_total, 'started_at': run.started_at.isoformat() if run.started_at else None,
                'finished_at': run.finished_at.isoformat() if run.finished_at else None, 'products': rows}
            if len(json.dumps(payload,ensure_ascii=False).encode('utf-8')) > 24*1024*1024:
                raise CommandError('Use --export-directory for large source content.')
            path = Path(options['export_path']).resolve()
            with gzip.open(path, 'wt', encoding='utf-8') as stream:
                json.dump(payload, stream, ensure_ascii=False)
            os.chmod(path, 0o600)
            self.stdout.write(f'Exported {len(rows)} original-source products; no credentials or business records.')
            return
        self.import_file(Path(options['import_path']).resolve())

    def export_directory(self, run_id, directory):
        run=SupplierRecollectionRun.objects.select_related('supplier').get(pk=run_id)
        root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
        through=run.products.order_by('-pk').values_list('pk',flat=True).first() or 0
        source_total=run.products.filter(pk__lte=through).count()
        base={'format':'cheradip-original-source-v1','run_id':str(run.pk),
              'supplier':{'id':run.supplier_id,'website':run.supplier.website},'mode':run.mode,
              'status':run.status,'coverage':run.coverage,'counts':run.counts,'errors':run.errors,
              'expected_total':run.expected_total,'source_total_products':source_total,
              'started_at':run.started_at.isoformat() if run.started_at else None,
              'finished_at':run.finished_at.isoformat() if run.finished_at else None}
        parts=[];rows=[];size=0
        def write_part(final=False):
            path=root/f'part-{len(parts)+1:05d}.json.gz'
            with gzip.open(path,'wt',encoding='utf-8') as stream:
                json.dump({**base,'products':rows,'transfer':{'final':final}},stream,ensure_ascii=False)
            os.chmod(path,0o600)
            with path.open('rb') as stream:
                checksum=hashlib.file_digest(stream,'sha256').hexdigest()
            parts.append({'file':path.name,'sha256':checksum,'products':len(rows)})
        def bounded_products():
            # MySQL buffers query results even with QuerySet.iterator(). Use
            # keyset pages so neither machine materialises the whole catalogue.
            after=0
            while True:
                page=list(run.products.filter(pk__gt=after,pk__lte=through).order_by('pk')[:25])
                if not page: return
                for product in page: yield product
                after=page[-1].pk
        for product in bounded_products():
            media=[{'url':m.original_url,'kind':m.kind,'role':m.role,'variant_id':m.variant_id,'alt':m.alt_text,
                    'metadata':{k:v for k,v in m.metadata.items() if k not in
                      ('verified_image','cached_name','sha256','width','height','verified_run_id','verified_at')}} for m in product.media.filter(last_run=run)]
            row={**{f:getattr(product,f) for f in FIELDS},'media':media,'observed_at':product.observed_at.isoformat()}
            row_size=len(json.dumps(row,ensure_ascii=False).encode('utf-8'))
            if rows and (len(rows)>=100 or size+row_size>24*1024*1024):
                write_part();rows=[];size=0
            rows.append(row);size+=row_size
        write_part(final=True)
        manifest=root/'manifest.json'
        manifest.write_text(json.dumps({'format':'cheradip-source-parts-v1','run_id':str(run.pk),
            'source_products':source_total,'parts':parts},indent=2),encoding='utf-8')
        os.chmod(manifest,0o600)
        self.stdout.write(f'Exported {source_total} original-source products in {len(parts)} bounded parts; no credentials or business records.')

    def import_file(self, path):
        if path.stat().st_size > 64 * 1024 * 1024:
            raise CommandError('Source bundle exceeds the reviewed transfer limit.')
        with gzip.open(path, 'rb') as stream:
            body=stream.read(48*1024*1024+1)
        if len(body)>48*1024*1024:
            raise CommandError('Expanded source bundle is too large; re-export with --export-directory.')
        payload=json.loads(body)
        del body
        if payload.get('format') != 'cheradip-original-source-v1' or payload.get('mode') != 'full':
            raise CommandError('Invalid original-source bundle.')
        supplier = Supplier.objects.get(pk=payload['supplier']['id'], website=payload['supplier']['website'], enabled=True, terms_confirmed=True)
        validated = [(validate_record(p), parse_datetime(p['observed_at'])) for p in payload['products']]
        if any(observed is None or observed.tzinfo is None for (_, observed) in validated):
            raise CommandError('Original observation timestamps are required; transfer must not claim a fresh check.')
        with transaction.atomic(using='ecommerce'):
            run, _ = SupplierRecollectionRun.objects.get_or_create(pk=payload['run_id'], defaults={'supplier': supplier, 'mode': 'full'})
            if run.supplier_id != supplier.pk:
                raise CommandError('Source run identity conflicts with target. No data replaced.')
            for (data, media), observed in validated:
                existing = SupplierSourceProduct.objects.filter(supplier=supplier, source_key=data['source_key']).first()
                if existing and existing.observed_at >= observed:
                    continue
                product, _ = SupplierSourceProduct.objects.update_or_create(supplier=supplier, source_key=data['source_key'],
                    defaults={**data, 'observed_at': observed, 'last_run': run})
                for image in media:
                    SupplierSourceMedia.objects.update_or_create(product=product, media_key=image['media_key'],
                        defaults={**image, 'last_run': run, 'last_seen_at': observed})
            imported_total=run.products.count()
            final=payload.get('transfer',{}).get('final',True) and imported_total>=payload.get('source_total_products',len(validated))
            run.status, run.coverage, run.counts = payload['status'] if final else 'paused', dict(payload['coverage']), payload['counts']
            if not final:
                run.coverage.update(full_traversal=False,transfer_pending=True,source_status=payload['status'])
            run.expected_total, run.processed, run.discovered = payload['expected_total'], imported_total, imported_total
            run.errors=payload.get('errors',[])[:100]
            run.started_at = parse_datetime(payload['started_at']) if payload.get('started_at') else None
            run.finished_at = parse_datetime(payload['finished_at']) if payload.get('finished_at') else None
            run.activity = 'Original source observations transferred; original timestamps preserved, no shop/customer/order replacement'
            run.save()
        self.stdout.write(f'Imported {len(validated)} original-source observations into run {run.pk}; no shop/customer/order records copied.')
