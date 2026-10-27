"""Catalogue-only portable replication with stable identities and three-way fields.

Credentials, customer identities, carts, orders, payments and ledgers are outside
the transport allowlist. UUID references never assume equal database row IDs.
"""
import gzip
import hashlib
import json
import uuid
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models as db_models, transaction, connections
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from . import models


class PreciseJSONEncoder(DjangoJSONEncoder):
    def default(self,value):
        # Django's default encoder truncates datetimes to milliseconds. That
        # changes natural identities for microsecond-precision observations.
        if isinstance(value,datetime):return value.isoformat()
        return super().default(value)

DB = 'ecommerce'
NAMESPACE = uuid.UUID('81d9ca17-675d-4f18-bcc1-519b7aa17929')
NAMES = ('Supplier', 'Category', 'Brand', 'DeliverySettings', 'SupplierPolicy', 'SupplierRecollectionRun', 'SupplierSourceProduct',
         'SupplierSourceMedia', 'SupplierRecollectionItem', 'Product', 'ProductVariant', 'ProductImage', 'SupplierOffer',
         'SupplierEvidence', 'SupplierDecision', 'SupplierResearchBatch', 'SupplierResearchItem')
SKIP = {'id', 'created_at', 'updated_at', 'current_decision', 'import_key',
        'credentials_ciphertext', 'credential_expires_at'}
SUPPLIER_FIELDS = {'name', 'website', 'enabled', 'connector', 'terms_confirmed', 'terms_note', 'health', 'last_success_at'}
POLICY_FIELDS = {'evidence_days','retention_days','revision','catalogue_mode','catalogue_revision','last_nightly_date'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, cls=DjangoJSONEncoder, ensure_ascii=False).encode()).hexdigest()


def field_hashes(values):
    output = {key:digest(value) for key,value in values.items()}
    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                nested = path + '/' + json.dumps(key)
                output[nested] = digest(child)
                walk(child, nested)
    walk(values.get('attributes'), 'attributes')
    return output


def merge_attributes(current, incoming, baseline, incoming_wins, path='attributes', local_baseline=None):
    result = dict(current)
    for key in current.keys() | incoming.keys():
        nested = path + '/' + json.dumps(key)
        old = baseline.get(nested)
        if key not in incoming:
            if old is not None and (digest(current[key]) == old or incoming_wins): result.pop(key, None)
        elif key not in current:
            # The receiver may have learned and then removed this field after
            # the sender exported its snapshot. Its own baseline proves that
            # absence is a deletion, not an independent missing field.
            locally_deleted=nested in (local_baseline or {})
            if incoming_wins or (old is None and not locally_deleted): result[key] = incoming[key]
        elif isinstance(current[key],dict) and isinstance(incoming[key],dict):
            result[key] = merge_attributes(current[key], incoming[key], baseline, incoming_wins, nested,local_baseline)
        elif old is not None and digest(incoming[key]) == old:
            continue
        elif old is not None and digest(current[key]) == old or incoming_wins:
            result[key] = incoming[key]
    return result


class Codec:
    def __init__(self):
        # Hundreds of thousands of per-field hash dictionaries must not all
        # occupy RAM together on the production server. Load a record's
        # baseline only while serializing that record.
        rows = list(models.CatalogSyncIdentity.objects.using(DB).only('uid','model_name','object_pk').annotate(
            alias_uids=db_models.F('field_hashes___sync_aliases')))
        self.identities = {(r.model_name, r.object_pk): r for r in rows}
        self.by_uid = {str(r.uid): r for r in rows}
        for row in rows:
            for alias in getattr(row,'alias_uids',None) or []:self.by_uid[alias]=row
        self.pending = {}
        self.objects = {}

    def uid(self,row):
        return min([str(row.uid),*(getattr(row,'alias_uids',None) or [])])

    def identity(self, obj):
        name, pk = type(obj).__name__, str(obj.pk)
        if (name, pk) in self.identities:
            return self.identities[name, pk]
        if name == 'Supplier': natural = obj.website.rstrip('/').lower()
        elif name in ('Category', 'Brand'): natural = obj.slug
        elif name == 'Product':
            try:
                offer = obj.supplier_offer
                natural = [self.uid(self.identity(offer.supplier)), offer.external_id, offer.variant_id, offer.vendor_id, offer.warehouse_id]
            except models.SupplierOffer.DoesNotExist: natural = obj.slug
        elif name == 'ProductVariant': natural = [self.uid(self.identity(obj.product)), obj.sku]
        elif name == 'SupplierRecollectionRun': natural = pk
        elif name in ('DeliverySettings','SupplierPolicy'): natural = 'store-singleton'
        elif name == 'SupplierSourceProduct': natural = [self.uid(self.identity(obj.supplier)), obj.source_key]
        elif name == 'SupplierSourceMedia': natural = [self.uid(self.identity(obj.product)), obj.media_key]
        elif name == 'SupplierRecollectionItem': natural = [self.uid(self.identity(obj.run)), obj.source_key]
        elif name == 'ProductImage': natural = [self.uid(self.identity(obj.product)), obj.url,
            self.uid(self.identity(obj.variant)) if obj.variant_id else None]
        elif name == 'SupplierOffer': natural = [self.uid(self.identity(obj.supplier)), obj.external_id,
            obj.variant_id, obj.vendor_id, obj.warehouse_id]
        elif name == 'SupplierEvidence': natural = [self.uid(self.identity(obj.offer)), obj.seller, obj.url, obj.observed_at.isoformat()]
        elif name == 'SupplierDecision': natural = [self.uid(self.identity(obj.offer)), obj.fingerprint, obj.created_at.isoformat()]
        elif name == 'SupplierResearchBatch': natural = pk
        elif name == 'SupplierResearchItem': natural = self.uid(self.identity(obj.offer))
        else: raise ValueError('Model is outside the catalogue sync scope.')
        uid = uuid.uuid5(NAMESPACE, name + ':' + json.dumps(natural, sort_keys=True))
        row = self.by_uid.get(str(uid))
        if row is None:
            row = models.CatalogSyncIdentity(uid=uid, model_name=name, object_pk=pk, field_hashes={})
            self.pending[str(uid)] = row
            self.by_uid[str(uid)] = row
        self.identities[name, pk] = row
        return row

    def flush(self):
        models.CatalogSyncIdentity.objects.using(DB).bulk_create(list(self.pending.values()), ignore_conflicts=True, batch_size=500)
        self.pending.clear()

    def accept_identity(self,record,object_pk):
        hashes=field_hashes(record['fields'])
        row=self.by_uid.get(record['uid']) or self.identities.get((record['model'],str(object_pk)))
        actual_uid=str(row.uid) if row else record['uid']
        aliases=sorted(({record['uid'],*(getattr(row,'alias_uids',None) or [])}-{actual_uid}))
        if aliases:hashes['_sync_aliases']=aliases
        values={'model_name':record['model'],'object_pk':str(object_pk),'field_hashes':hashes}
        changed=models.CatalogSyncIdentity.objects.using(DB).filter(uid=actual_uid).update(**values)
        if not changed:row=models.CatalogSyncIdentity.objects.using(DB).create(uid=actual_uid,**values)
        else:
            row=models.CatalogSyncIdentity(uid=actual_uid,**values);row._state.adding=False
        row.alias_uids=aliases
        # Import consumes each transport identity once; the persisted hashes
        # are needed by future exports, not by this in-memory reference index.
        row.__dict__.pop('field_hashes',None)
        self.pending.pop(record['uid'],None);self.pending.pop(actual_uid,None)
        for uid in (actual_uid,*aliases):self.by_uid[uid]=row
        self.identities[record['model'],str(object_pk)]=row
        return row

    def portable_attributes(self, obj):
        attrs = dict(obj.attributes or {})
        attrs.pop('_catalog_sync_pending_status', None)
        if isinstance(attrs.get('_retail_pricing'), dict):
            variants = {str(v.pk): self.uid(self.identity(v)) for v in obj.variants.all()}
            attrs['_retail_pricing'] = {'sync:' + variants[k] if k in variants else k: v
                for k, v in attrs['_retail_pricing'].items()}
        return attrs

    def fields(self, obj):
        values = {}
        for field in obj._meta.concrete_fields:
            if field.name in SKIP: continue
            if isinstance(obj, models.Supplier) and field.name not in SUPPLIER_FIELDS: continue
            if isinstance(obj, models.SupplierPolicy) and field.name not in POLICY_FIELDS: continue
            if field.is_relation:
                pk = getattr(obj,field.attname)
                identity = self.identities.get((field.related_model.__name__,str(pk))) if pk is not None else None
                value = ({'ref':self.uid(identity or self.identity(getattr(obj,field.name)))} if pk is not None else None)
            else:
                value = getattr(obj, field.name)
            if field.name == 'attributes' and isinstance(obj, models.Product):
                value = self.portable_attributes(obj)
            elif field.name == 'status' and isinstance(obj, models.Product):
                value = (obj.attributes or {}).get('_catalog_sync_pending_status', value)
            values[field.name] = value
        if isinstance(obj, models.Product):
            values['secondary_categories'] = sorted(self.uid(self.identity(c)) for c in obj.secondary_categories.all())
        return json.loads(json.dumps(values, cls=PreciseJSONEncoder))

    def record(self, obj):
        row = self.identity(obj)
        record = {'model': type(obj).__name__, 'uid': self.uid(row), 'pk_hint': str(obj.pk),
            'fields': self.fields(obj), 'base': {key:value for key,value in row.field_hashes.items() if key!='_sync_aliases'},
            'updated_at': obj.updated_at.isoformat(), 'created_at': obj.created_at.isoformat()}
        if str(row.uid) not in self.pending:row.__dict__.pop('field_hashes',None)
        if isinstance(obj, models.Product):
            try:
                offer = obj.supplier_offer
                record['supplier_identity'] = {'supplier_uid':self.uid(self.identity(offer.supplier)),
                    'external_id':offer.external_id,'variant_id':offer.variant_id,'vendor_id':offer.vendor_id,'warehouse_id':offer.warehouse_id}
            except models.SupplierOffer.DoesNotExist: pass
        if isinstance(obj, models.ProductVariant):
            try:
                offer = obj.product.supplier_offer
                record['stock_observed_at'] = offer.observed_at.isoformat() if offer.observed_at else None
            except models.SupplierOffer.DoesNotExist: pass
        if isinstance(obj, models.SupplierOffer) and obj.current_decision_id:
            record['current_decision_uid'] = self.uid(self.identity(obj.current_decision))
        return record

    def find(self, row):
        name, fields = row['model'], row['fields']
        cls = getattr(models, name)
        identity = self.by_uid.get(row['uid'])
        if identity:
            found = cls.objects.using(DB).filter(pk=identity.object_pk).first()
            if found: return found
        if name == 'Product' and row.get('supplier_identity'):
            source = dict(row['supplier_identity'])
            supplier = self.by_uid.get(source.pop('supplier_uid'))
            if supplier:
                offer = models.SupplierOffer.objects.using(DB).filter(supplier_id=supplier.object_pk, **source).first()
                if offer and offer.imported_product_id:
                    return offer.imported_product
        if name in ('Category', 'Brand', 'Product'): lookup = {'slug': fields['slug']}
        elif name == 'Supplier': lookup = {'website': fields['website']}
        elif name == 'ProductVariant': lookup = {'sku': fields['sku'], 'product':self.reference_pk(fields['product'])}
        elif name in ('SupplierRecollectionRun','SupplierResearchBatch'): lookup = {'pk': row['pk_hint']}
        elif name in ('DeliverySettings','SupplierPolicy'): lookup = {'pk':1}
        elif name == 'SupplierDecision': lookup = {'offer':self.reference_pk(fields['offer']), 'fingerprint':fields['fingerprint'], 'created_at':row['created_at']}
        else:
            keys = {'SupplierSourceProduct': ('supplier', 'source_key'),
                'SupplierSourceMedia': ('product', 'media_key'),
                'SupplierRecollectionItem': ('run', 'source_key'),
                'ProductImage': ('product', 'url', 'variant'),
                'SupplierEvidence': ('offer','seller','url','observed_at'),
                'SupplierResearchItem': ('offer',),
                'SupplierOffer': ('supplier', 'external_id', 'variant_id', 'vendor_id', 'warehouse_id')}[name]
            lookup = {key: self.reference_pk(fields[key]) if cls._meta.get_field(key).is_relation else fields[key] for key in keys}
        found = cls.objects.using(DB).filter(**lookup).first()
        if name == 'Product' and found and row.get('supplier_identity'):
            identity = self.identity(found)
            if row['uid'] not in (str(identity.uid),*(getattr(identity,'alias_uids',None) or [])):
                return None
        return found

    def resolve(self, value):
        if isinstance(value, dict) and set(value) == {'ref'}:
            row = self.by_uid.get(value['ref'])
            if row is None: raise ValueError('A required catalogue dependency is absent; import stopped.')
            return getattr(models, row.model_name).objects.using(DB).get(pk=row.object_pk)
        return value

    def reference_pk(self, value, model=None):
        if value is None:return None
        if not isinstance(value,dict) or set(value)!={'ref'}:raise ValueError('Invalid catalog relation.')
        row=self.by_uid.get(value['ref'])
        if row is None or (model and row.model_name!=model.__name__):raise ValueError('A required catalog dependency is absent or mismatched.')
        return row.object_pk


def export_catalog(path, since=None):
    codec, seen, count = Codec(), set(), 0
    item_pk_reference=db_models.functions.Cast(db_models.OuterRef('pk'), db_models.CharField())
    connection=connections[DB]
    if since and connection.vendor=='mysql':
        # CAST inherits the connection collation, which can differ from this
        # existing registry column. Collate the value, not the indexed column.
        with connection.cursor() as cursor:
            cursor.execute('SHOW FULL COLUMNS FROM '+connection.ops.quote_name(models.CatalogSyncIdentity._meta.db_table)+' LIKE %s',['object_pk'])
            info=cursor.fetchone()
        collation=info[2] if info else None
        if collation:item_pk_reference=db_models.functions.Collate(item_pk_reference,collation)
    path = Path(path)
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        stream.write(json.dumps({'format': 'cheradip-catalog-sync-v1', 'at': timezone.now().isoformat()}) + '\n')

        def emit(obj):
            nonlocal count
            uid = codec.uid(codec.identity(obj))
            if uid in seen: return
            seen.add(uid)
            for field in obj._meta.concrete_fields:
                if field.is_relation and field.name not in SKIP:
                    parent = getattr(obj, field.name)
                    if parent is not None: emit(parent)
            if isinstance(obj, models.Product):
                for category in obj.secondary_categories.all(): emit(category)
            stream.write(json.dumps(codec.record(obj), cls=DjangoJSONEncoder, ensure_ascii=False) + '\n')
            count += 1
            if count % 500 == 0: codec.flush()

        for name in NAMES:
            cls = getattr(models, name)
            after = None
            while True:
                qs = cls.objects.using(DB).order_by('pk')
                # Transport reads are bounded, but must not make an extra
                # database round trip for every image's supplier/run parent.
                if name == 'Product':
                    qs = qs.prefetch_related('supplier_offer__supplier','secondary_categories','variants')
                # Prefetch related rows in separate bounded queries. Joining
                # every raw source JSON onto its image rows can force MySQL
                # to materialize enormous temporary sorts on small servers.
                relations = [f.name for f in cls._meta.concrete_fields if f.is_relation and f.name not in SKIP]
                if relations: qs = qs.prefetch_related(*relations)
                if since:
                    if name == 'SupplierRecollectionItem':
                        # This allowlist addition must backfill older per-item
                        # failures/checkpoints even after the first full sync.
                        # An empty export-only baseline is not proof of delivery.
                        registered = models.CatalogSyncIdentity.objects.using(DB).filter(
                            model_name=name,
                            object_pk=item_pk_reference,
                        ).exclude(field_hashes={})
                        qs = qs.annotate(_sync_known=db_models.Exists(registered)).filter(
                            db_models.Q(updated_at__gte=since) | db_models.Q(_sync_known=False))
                    else:
                        qs = qs.filter(updated_at__gte=since)
                if after is not None: qs = qs.filter(pk__gt=after)
                page = list(qs[:50])
                if not page: break
                for obj in page: emit(obj)
                after = page[-1].pk
        codec.flush()
    return {'records': count, 'file': str(path)}


@contextmanager
def import_transactions():
    connection=connections[DB]
    batched=connection.get_autocommit() and not connection.in_atomic_block
    if batched:connection.set_autocommit(False)
    def checkpoint(number):
        if batched and number and number%200==0:connection.commit()
    try:
        yield checkpoint
        if batched:connection.commit()
    except BaseException:
        if batched:connection.rollback()
        raise
    finally:
        if batched:connection.set_autocommit(True)


def import_catalog(path,after_record=0):
    codec, counts, pending_attributes = Codec(), {'created': 0, 'updated': 0, 'unchanged':0, 'conflict_count':0, 'conflicts': []}, []
    pending_decisions = []
    received_variants = []
    received_media=[]
    def conflict(detail):
        counts['conflict_count']+=1
        if len(counts['conflicts'])<100:counts['conflicts'].append(detail)
    with import_transactions() as checkpoint, gzip.open(path, 'rt', encoding='utf-8') as stream:
        if json.loads(stream.readline()).get('format') != 'cheradip-catalog-sync-v1':
            raise ValueError('Unsupported catalogue transport.')
        for row_number,line in enumerate(stream,1):
            checkpoint(row_number-1)
            if len(line) > 12 * 1024 * 1024: raise ValueError('Catalogue row exceeds the bounded transfer size.')
            record = json.loads(line)
            if record['model'] not in NAMES: raise ValueError('Non-catalogue model refused.')
            if row_number<=after_record:
                identity=codec.by_uid.get(record['uid'])
                if identity is None:raise ValueError('Committed import checkpoint is missing an identity; restart without resume.')
                if record['model']=='Product':pending_attributes.append((int(identity.object_pk),None))
                if record['model']=='ProductVariant':received_variants.append(int(identity.object_pk))
                if record['model']=='SupplierSourceMedia':received_media.append(int(identity.object_pk))
                if record['model']=='SupplierOffer' and record.get('current_decision_uid'):
                    pending_decisions.append((int(identity.object_pk),record['current_decision_uid']))
                continue
            if row_number>1 and (row_number-1)%1000==0:
                Path(path).with_suffix('.import-progress.json').write_text(json.dumps({
                    'records':row_number-1,'model':record['model'],'created':counts['created'],
                    'updated':counts['updated'],'unchanged':counts['unchanged'],
                    'bundle_bytes':Path(path).stat().st_size,'bundle_mtime_ns':Path(path).stat().st_mtime_ns,
                    'updated_at':timezone.now().isoformat()}),encoding='utf-8')
            incoming_at = parse_datetime(record['updated_at'])
            if incoming_at is None or timezone.is_naive(incoming_at): raise ValueError('An aware source timestamp is required.')
            with transaction.atomic(using=DB,savepoint=False):
                obj = codec.find(record)
                created = obj is None
                cls = getattr(models, record['model'])
                if obj is not None: obj = cls.objects.using(DB).select_for_update().get(pk=obj.pk)
                current = codec.fields(obj) if obj else {}
                incoming, merged = dict(record['fields']), dict(current)
                if obj and incoming==current and obj.updated_at>=incoming_at:
                    # Most images are identical on the first reconciliation.
                    # Establish the comparison baseline without rewriting the
                    # model row or loading large foreign-key source documents.
                    codec.accept_identity(record,obj.pk)
                    if cls is models.Product:pending_attributes.append((obj.pk,current['status']))
                    if cls is models.ProductVariant:received_variants.append(obj.pk)
                    if cls is models.SupplierSourceMedia:received_media.append(obj.pk)
                    if cls is models.SupplierOffer and record.get('current_decision_uid'):
                        pending_decisions.append((obj.pk,record['current_decision_uid']))
                    counts['unchanged']+=1
                    continue
                if cls is models.ProductVariant:
                    parent = codec.resolve(incoming['product'])
                    if (parent.attributes or {}).get('manual_supplier_catalogue'):
                        # Per-server accepted orders are outside catalog sync.
                        # Rebuild available units from the shared supplier fact
                        # after offer dependencies arrive, minus OUR reservations.
                        incoming.pop('stock',None)
                if cls is models.Product:
                    collision = cls.objects.using(DB).filter(slug=incoming['slug'])
                    if obj: collision = collision.exclude(pk=obj.pk)
                    collision = collision.first()
                    if collision:
                        other_uid = codec.uid(codec.identity(collision))
                        if record['uid'] < other_uid:
                            cls.objects.using(DB).filter(pk=collision.pk).update(
                                slug=incoming['slug'][:235]+'-sync-'+other_uid[:8], updated_at=timezone.now())
                        else:
                            incoming['slug'] = incoming['slug'][:235]+'-sync-'+record['uid'][:8]
                        conflict({'model':'Product','uid':record['uid'],'field':'slug','rule':'distinct_supplier_identity'})
                if cls is models.ProductVariant:
                    collision = cls.objects.using(DB).filter(sku=incoming['sku'])
                    if obj: collision = collision.exclude(pk=obj.pk)
                    collision = collision.first()
                    if collision:
                        other_uid = codec.uid(codec.identity(collision))
                        if record['uid'] < other_uid:
                            cls.objects.using(DB).filter(pk=collision.pk).update(
                                sku=incoming['sku'][:100]+'-sync-'+other_uid[:8], updated_at=timezone.now())
                        else:
                            incoming['sku'] = incoming['sku'][:100]+'-sync-'+record['uid'][:8]
                        conflict({'model':'ProductVariant','uid':record['uid'],'field':'sku','rule':'deterministic_unique_sku'})
                base = record.get('base') or {}
                allowed = {f.name for f in cls._meta.concrete_fields if f.name not in SKIP}
                if cls is models.Supplier: allowed &= SUPPLIER_FIELDS
                if cls is models.SupplierPolicy: allowed &= POLICY_FIELDS
                if cls is models.Product: allowed.add('secondary_categories')
                if set(incoming) - allowed: raise ValueError('Unexpected catalogue fields refused.')
                # A newly repaired relationship is not a newer supplier stock
                # observation. Preserve actual source observation chronology.
                stale_source_fields = set()
                if obj and cls is models.SupplierSourceMedia:
                    seen=parse_datetime(incoming.get('last_seen_at') or '')
                    if obj.last_seen_at and (not seen or seen<obj.last_seen_at):
                        # A later cached-byte verification is not a later
                        # gallery observation; do not restore its older run.
                        stale_source_fields={'last_run','last_seen_at','role','position','variant_id','original_url'}
                if obj and cls in (models.SupplierOffer, models.SupplierSourceProduct):
                    observed = parse_datetime(incoming.get('observed_at') or '')
                    target_observed = obj.observed_at
                    if cls is models.SupplierSourceProduct:
                        observed = parse_datetime((incoming.get('extra') or {}).get('price_stock_checked_at') or '') or observed
                        target_observed = parse_datetime((obj.extra or {}).get('price_stock_checked_at') or '') or target_observed
                    if target_observed and (not observed or observed < target_observed):
                        stale_source_fields = ({'source_price','quantity','availability','observed_at','currency'} if cls is models.SupplierOffer
                            else {'prices','stock','observed_at','last_run'})
                if obj and cls is models.ProductVariant and record.get('stock_observed_at'):
                    try:
                        target_observed = obj.product.supplier_offer.observed_at
                        if target_observed and parse_datetime(record['stock_observed_at']) < target_observed:
                            stale_source_fields = {'stock','cost_price','allow_backorder'}
                    except models.SupplierOffer.DoesNotExist: pass
                for field, value in incoming.items():
                    if field in stale_source_fields: continue
                    if value == current.get(field): continue
                    old_hash = base.get(field)
                    incoming_changed = old_hash is None or digest(value) != old_hash
                    current_changed = obj is not None and (old_hash is None or digest(current.get(field)) != old_hash)
                    if not incoming_changed: continue
                    local_baseline={}
                    if obj and field=='attributes' and isinstance(value,dict) and isinstance(current.get(field),dict):
                        local_baseline=codec.identity(obj).field_hashes
                        present=field_hashes({'attributes':current[field]})
                        # An add followed by a delete can return the whole JSON
                        # to the sender's old hash. It is still a local deletion
                        # if this receiver had already observed that nested key.
                        current_changed=current_changed or any(k.startswith('attributes/') and k not in present for k in local_baseline)
                    if current_changed:
                        conflict({'model': record['model'], 'uid': record['uid'], 'field': field,
                            'rule': 'latest_timestamp_then_value_hash'})
                        incoming_wins = obj.updated_at < incoming_at or (obj.updated_at == incoming_at and digest(current.get(field)) <= digest(value))
                        if field == 'attributes' and isinstance(value,dict) and isinstance(current.get(field),dict) and any(k.startswith('attributes/') for k in base):
                            merged[field] = merge_attributes(current[field], value, base, incoming_wins,local_baseline=local_baseline)
                            continue
                        if not incoming_wins:
                            continue
                    merged[field] = value
                values = {}
                for key,value in merged.items():
                    if key=='secondary_categories':continue
                    field=cls._meta.get_field(key)
                    if field.is_relation:
                        values[field.attname]=codec.reference_pk(value,field.related_model)
                    else:values[key]=value
                if created:
                    if cls in (models.SupplierRecollectionRun,models.SupplierResearchBatch): values['id'] = record['pk_hint']
                    if cls in (models.DeliverySettings,models.SupplierPolicy): values['id'] = 1
                    if cls is models.ProductVariant:
                        collision = cls.objects.using(DB).filter(sku=values['sku']).first()
                        if collision:
                            other_uid = codec.uid(codec.identity(collision))
                            if record['uid'] < other_uid:
                                cls.objects.using(DB).filter(pk=collision.pk).update(sku=values['sku'][:100]+'-sync-'+other_uid[:8])
                            else:
                                values['sku'] = values['sku'][:100]+'-sync-'+record['uid'][:8]
                            merged['sku'] = values['sku']
                            conflict({'model':'ProductVariant','uid':record['uid'], 'field':'sku', 'rule':'deterministic_unique_sku'})
                    # save_base preserves PK retrieval on MySQL and bypasses
                    # Product.save publication hooks during dependency staging.
                    obj = cls(**values)
                    if cls is models.Product:
                        obj.status = 'draft'
                        obj.attributes = {**(obj.attributes or {}), '_catalog_sync_pending_status':values.get('status','draft')}
                    obj.save_base(using=DB)
                    counts['created'] += 1
                elif merged != current:
                    cls.objects.using(DB).filter(pk=obj.pk).update(**values)
                    counts['updated'] += 1
                stamp = incoming_at if created else max(obj.updated_at, incoming_at)
                timestamps = {'updated_at': stamp}
                if created: timestamps['created_at'] = parse_datetime(record['created_at'])
                cls.objects.using(DB).filter(pk=obj.pk).update(**timestamps)
                if cls is models.Product:
                    obj.secondary_categories.set([codec.by_uid[uid].object_pk for uid in merged.get('secondary_categories', [])])
                    pending_attributes.append((obj.pk, merged.get('status', obj.status)))
                if cls is models.SupplierOffer and record.get('current_decision_uid'):
                    pending_decisions.append((obj.pk, record['current_decision_uid']))
                if cls is models.ProductVariant:
                    received_variants.append(obj.pk)
                if cls is models.SupplierSourceMedia:received_media.append(obj.pk)
                # Retained local edits are NOT yet known to the sender. Its
                # actual snapshot is the comparison baseline for the next send.
                codec.accept_identity(record,obj.pk)
    # Convert portable variant UUIDs back to the receiving database's row IDs.
    codec.flush()
    for offer_id, uid in pending_decisions:
        identity = codec.by_uid.get(uid)
        if identity:
            decision = models.SupplierDecision.objects.using(DB).only('pk','created_at').get(pk=identity.object_pk)
            offer = models.SupplierOffer.objects.using(DB).select_related('current_decision').only('pk','current_decision','current_decision__created_at').get(pk=offer_id)
            if not offer.current_decision_id or decision.created_at >= offer.current_decision.created_at:
                models.SupplierOffer.objects.using(DB).filter(pk=offer_id).update(current_decision=decision)
    desired_status = dict(pending_attributes)
    for product in models.Product.objects.using(DB).filter(pk__in=desired_status).only('pk','attributes','status').iterator(chunk_size=200):
        attrs = dict(product.attributes or {})
        had_pending = '_catalog_sync_pending_status' in attrs
        attrs.pop('_catalog_sync_pending_status', None)
        pricing = attrs.get('_retail_pricing')
        if isinstance(pricing, dict):
            restored = {}
            for key, value in pricing.items():
                identity = codec.by_uid.get(key.removeprefix('sync:')) if key.startswith('sync:') else None
                restored[identity.object_pk if identity else key] = value
            attrs['_retail_pricing'] = restored
        if had_pending or attrs != product.attributes:
            models.Product.objects.using(DB).filter(pk=product.pk).update(attributes=attrs)
        target_status=desired_status[product.pk] or (product.attributes or {}).get('_catalog_sync_pending_status')
        if target_status and product.status != target_status:
            models.Product.objects.using(DB).filter(pk=product.pk).update(status=target_status)
    reconcile_received_stock(received_variants)
    if received_media:
        from .source_media_repair import repair_media_membership
        repair_media_membership(received_media,apply=True)
    return counts


def reconcile_received_stock(variant_ids):
    """Source stock is shared; accepted-order reservations belong to this node."""
    from django.db.models import Sum
    ids=sorted(set(variant_ids))
    for start in range(0,len(ids),250):
        batch=ids[start:start+250]
        # Checkout locks variants too. Read reservations after acquiring these
        # locks, so a concurrent accepted order cannot be overwritten here.
        with transaction.atomic(using=DB):
            variants=list(models.ProductVariant.objects.using(DB).select_for_update().filter(pk__in=batch).order_by('pk'))
            products={p.pk:p for p in models.Product.objects.using(DB).filter(pk__in={v.product_id for v in variants}).only('pk','attributes')}
            offers={o.imported_product_id:o for o in models.SupplierOffer.objects.using(DB).filter(imported_product_id__in=products).only('imported_product_id','quantity','availability')}
            reserved=dict(models.OrderItem.objects.using(DB).filter(variant_id__in=batch,
                order__status__in=('pending','confirmed','processing')).values('variant_id').annotate(n=Sum('quantity')).values_list('variant_id','n'))
            changed=[]
            for variant in variants:
                if not (products[variant.product_id].attributes or {}).get('manual_supplier_catalogue'):continue
                offer=offers.get(variant.product_id)
                if not offer:continue
                quantity=offer.quantity if offer.availability=='in_stock' and not variant.allow_backorder else 0
                available=max(0,(quantity or 0)-reserved.get(variant.pk,0))
                if variant.stock!=available:
                    variant.stock=available;changed.append(variant)
            if changed:models.ProductVariant.objects.using(DB).bulk_update(changed,['stock'],batch_size=250)
