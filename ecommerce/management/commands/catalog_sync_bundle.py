import json
import re
import tarfile
import gzip
from pathlib import Path
from django.conf import settings
from django.db import connections
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from ecommerce.catalog_sync import export_catalog, import_catalog


class Command(BaseCommand):
    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--export', dest='export_path')
        group.add_argument('--import', dest='import_path')
        group.add_argument('--asset-list')
        group.add_argument('--pack-assets')
        group.add_argument('--unpack-assets')
        group.add_argument('--rebase-received', help='Repair sync comparison baselines from a completed received snapshot, without changing catalog records.')
        parser.add_argument('--exclude-assets')
        parser.add_argument('--bundle-input')
        parser.add_argument('--since')
        parser.add_argument('--only-models', help='Comma-separated catalog model names for a bounded export; parent records are included automatically.')
        parser.add_argument('--recent-collection-items-only', action='store_true',
            help='With --since, transfer changed collection checks without retrying the historical item backfill.')
        parser.add_argument('--resume-import',action='store_true')

    def handle(self, *args, **options):
        from ecommerce.models import CatalogSyncIdentity
        connection = connections['ecommerce']
        if CatalogSyncIdentity._meta.db_table not in connection.introspection.table_names():
            with connection.schema_editor() as editor:
                editor.create_model(CatalogSyncIdentity)
        root = Path(settings.MEDIA_ROOT).resolve()
        if options['rebase_received']:
            from ecommerce.catalog_sync import field_hashes,NAMES
            changed=0;batch=[]
            def apply_batch():
                nonlocal changed
                identities={str(row.uid):row for row in CatalogSyncIdentity.objects.using('ecommerce').filter(uid__in=[record['uid'] for record in batch])}
                rows=[]
                for record in batch:
                    identity=identities.get(record['uid'])
                    if identity and identity.model_name==record['model']:
                        aliases=(identity.field_hashes or {}).get('_sync_aliases')
                        identity.field_hashes=field_hashes(record['fields'])
                        if aliases:identity.field_hashes['_sync_aliases']=aliases
                        rows.append(identity)
                CatalogSyncIdentity.objects.using('ecommerce').bulk_update(rows,['field_hashes'],batch_size=100)
                changed+=len(rows);batch.clear()
            with gzip.open(options['rebase_received'],'rt',encoding='utf-8') as stream:
                if json.loads(next(stream)).get('format')!='cheradip-catalog-sync-v1':raise ValueError('Unsupported catalog snapshot.')
                for line in stream:
                    record=json.loads(line)
                    if record['model'] not in NAMES:raise ValueError('Non-catalog baseline refused.')
                    batch.append(record)
                    if len(batch)>=100:apply_batch()
                if batch:apply_batch()
            self.stdout.write(json.dumps({'comparison_baselines_repaired':changed,'catalog_records_changed':0}));return
        photos = root / 'supplier_products'
        valid = re.compile(r'^(?:supplier_products/[a-f0-9]{64}\.(?:jpg|png|webp|gif|avif)|ecommerce/products/\d{4}/\d{2}/[a-f0-9]{32}\.webp)$')
        if options['asset_list']:
            names = ['supplier_products/' + p.name for p in photos.glob('*') if p.is_file() and valid.fullmatch('supplier_products/' + p.name)]
            names.extend(p.relative_to(root).as_posix() for p in (root/'ecommerce'/'products').rglob('*.webp') if valid.fullmatch(p.relative_to(root).as_posix()))
            Path(options['asset_list']).write_text(json.dumps(names), encoding='utf-8')
            self.stdout.write(json.dumps({'assets': len(names)})); return
        if options['pack_assets']:
            existing = set(json.loads(Path(options['exclude_assets']).read_text())) if options['exclude_assets'] else set()
            required = set()
            with gzip.open(options['bundle_input'], 'rt', encoding='utf-8') as stream:
                next(stream)
                for line in stream:
                    record = json.loads(line)
                    if record['model'] == 'SupplierSourceMedia':
                        meta = record['fields'].get('metadata') or {}
                        name = meta.get('cached_name', '')
                        if meta.get('verified_image') and valid.fullmatch(name): required.add(name)
                    elif record['model'] == 'ProductImage':
                        from urllib.parse import urlsplit
                        name = urlsplit(record['fields'].get('url','')).path.split('/media/',1)[-1]
                        if valid.fullmatch(name): required.add(name)
            with tarfile.open(options['pack_assets'], 'w') as bundle:
                for name in sorted(required - existing):
                    path = root / name
                    if path.is_file(): bundle.add(path, arcname=name, recursive=False)
            self.stdout.write(json.dumps({'required_assets': len(required)})); return
        if options['unpack_assets']:
            count = 0
            photos.mkdir(parents=True, exist_ok=True)
            with tarfile.open(options['unpack_assets']) as bundle:
                for member in bundle:
                    if not member.isfile() or not valid.fullmatch(member.name) or member.size > 15*1024*1024:
                        raise ValueError('Unexpected media archive entry refused.')
                    target = root / member.name
                    if target.exists(): continue
                    data = bundle.extractfile(member).read(15*1024*1024+1)
                    import hashlib
                    if member.name.startswith('supplier_products/') and hashlib.sha256(data).hexdigest() != Path(member.name).stem:
                        raise ValueError('Product photo checksum mismatch.')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data); count += 1
            self.stdout.write(json.dumps({'photos_imported': count})); return
        after=0
        if options['import_path'] and options['resume_import']:
            path=Path(options['import_path']);progress=path.with_suffix('.import-progress.json')
            if progress.exists():
                saved=json.loads(progress.read_text());stat=path.stat()
                if (saved.get('bundle_bytes',stat.st_size)!=stat.st_size or
                    saved.get('bundle_mtime_ns',stat.st_mtime_ns)!=stat.st_mtime_ns or
                    stat.st_mtime>parse_datetime(saved['updated_at']).timestamp()):
                    raise ValueError('The snapshot changed after its checkpoint; restart without resume.')
                after=int(saved['records'])//200*200
        selected = [name.strip() for name in options['only_models'].split(',')] if options['only_models'] else None
        if (selected or options['recent_collection_items_only']) and not options['export_path']:
            raise ValueError('Export selection applies only to exports.')
        result = export_catalog(options['export_path'], parse_datetime(options['since']) if options['since'] else None,
            include_names=selected, backfill_collection_items=not options['recent_collection_items_only']) if options['export_path'] else import_catalog(options['import_path'],after_record=after)
        self.stdout.write(json.dumps(result))
