"""Validated full-source staging. Never imports orders or silently edits selling prices."""
import hashlib
import ipaddress
import json
import re
from urllib.parse import parse_qsl, urlsplit

from django.db import transaction
from django.utils import timezone
from .models import SupplierRecollectionRun, SupplierRecollectionItem, SupplierSourceProduct, SupplierSourceMedia

DB = 'ecommerce'
MAPPING_VERSION = 2
CACHE_PROOF_FIELDS = {'verified_image','cached_name','sha256','verified_run_id','verified_at'}
SECRET_KEYS = re.compile(r'(?:password|secret|authorization|cookie|csrf|nonce|access.?token|refresh.?token|api.?key|bearer)', re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def description_text(value):
    from html import unescape
    from lxml import html
    value=str(value or '')
    try:
        node=html.fragment_fromstring(value,create_parent='div')
        for child in node.xpath('.//script|.//style'):child.drop_tree()
        value=unescape(node.text_content()).strip()
    except (ValueError,TypeError):value=unescape(value).strip()
    if ' '.join(value.casefold().split()) in {'','n/a','na','none','null','undefined','-','no description','no description available'}:
        return ''
    return value


def preferred_description(source):
    return description_text(source.description) or description_text(source.short_description)


def reference_url(value):
    """Reference validation only; these URLs are not arbitrary server-fetch destinations."""
    value = str(value or '').strip()
    parts = urlsplit(value)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Only public HTTPS references without credentials are supported.')
    host = parts.hostname.lower()
    if host in ('localhost', 'localhost.localdomain') or host.endswith(('.local', '.lan', '.internal', '.localhost')):
        raise ValueError('Private source reference refused.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host:
            raise ValueError('Use a public hostname.')
    else:
        if not address.is_global:
            raise ValueError('Private source reference refused.')
    if any(SECRET_KEYS.search(key) or key.lower() in ('token', 'signature', 'sig', 'credential', 'expires', 'x-amz-signature') for key, _ in parse_qsl(parts.query)):
        raise ValueError('Session-bearing or expiring source reference refused.')
    if len(value) > 2000:
        raise ValueError('Source URL exceeds storage limit; review rather than truncating it.')
    return value


def product_data(value, depth=0):
    """Defence in depth; caller must supply a product object, never a login/profile response."""
    if depth > 40:
        raise ValueError('Product nesting exceeds the reviewed limit.')
    if isinstance(value, dict):
        return {str(k): product_data(v, depth + 1) for k, v in value.items() if not SECRET_KEYS.search(str(k)) and str(k).lower() != 'token'}
    if isinstance(value, list):
        return [product_data(v, depth + 1) for v in value]
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        try:
            return reference_url(value)
        except ValueError:
            return '[non-public or session-bearing reference omitted]'
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def source_key(external_id, vendor_id='', warehouse_id=''):
    if not str(external_id).strip():
        raise ValueError('An original supplier identifier or explicitly derived canonical URL key is required.')
    return digest([str(external_id), str(vendor_id), str(warehouse_id)])


def clean_media(values):
    if not isinstance(values, list) or len(values) > 1000:
        raise ValueError('Invalid media list or more than 1,000 media references; review without truncation.')
    result, seen, rejected = [], set(), []
    for position, entry in enumerate(values):
        if not isinstance(entry, dict):
            raise ValueError('Media must include provenance and an original URL.')
        try:
            url = reference_url(entry.get('url'))
            parts = urlsplit(url)
            if re.search(r'(?:^|[/_.-])(?:logo|placeholder|favicon)(?:[/_.-]|$)|cheradip\.(?:svg|png)', parts.path, re.I):
                raise ValueError('Brand artwork is not a product photo.')
            if entry.get('kind', 'image') not in ('image', 'video'):
                raise ValueError('Unsupported media kind.')
            key = digest([url, str(entry.get('variant_id') or ''), entry.get('kind', 'image')])
            if key in seen:
                continue  # Exact URL + variant relationship only, never filename/similarity-based deletion.
            seen.add(key)
            result.append({'media_key': key, 'kind': entry.get('kind', 'image'),
                'role': entry.get('role', 'main' if not result else 'gallery'), 'original_url': url,
                'variant_id': str(entry.get('variant_id') or ''), 'alt_text': str(entry.get('alt') or ''),
                'position': position, 'metadata': {k:v for k,v in product_data(entry.get('metadata') or {}).items() if k not in CACHE_PROOF_FIELDS}})
        except ValueError as exc:
            rejected.append({'position': position, 'reason': str(exc)})
    return result, rejected


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError('A full product source object is required.')
    if len(json.dumps(record, ensure_ascii=False, default=str).encode()) > 8 * 1024 * 1024:
        raise ValueError('Product exceeds the safe 8 MB limit; record as a failure, never silently truncate it.')
    title = str(record.get('title') or '').strip()
    if not title:
        raise ValueError('Original product title is missing.')
    external = str(record.get('external_id') or '').strip()
    vendor, warehouse = str(record.get('vendor_id') or ''), str(record.get('warehouse_id') or '')
    if max(map(len, (external, vendor, warehouse))) > 255:
        raise ValueError('Original identifier exceeds storage limit; review without truncation.')
    images, rejected = clean_media(record.get('media') or [])
    missing = []
    description = str(record.get('description') or '')
    short = str(record.get('short_description') or '')
    from django.utils.html import strip_tags
    from html import unescape
    if not description_text(description) and not description_text(short):
        missing.append('description')
    if not any(m['kind'] == 'image' and m['role'] in ('main', 'gallery', 'variant') for m in images):
        missing.append('product_images')
    if (record.get('extra') or {}).get('pending_identity_review'):
        missing.append('identity_review')
    data = dict(external_id=external, vendor_id=vendor, warehouse_id=warehouse,
        source_key=source_key(external, vendor, warehouse), url=reference_url(record.get('url')), title=title,
        sku=str(record.get('sku') or ''), description=description, short_description=short,
        quality={'missing': missing, 'rejected_media': rejected, 'mapping_version': MAPPING_VERSION})
    if len(data['sku']) > 500:
        raise ValueError('Original SKU exceeds storage limit; review without truncation.')
    for name, default in [('categories', []), ('specifications', {}), ('features', []), ('prices', {}),
                          ('stock', {}), ('variants', []), ('shipping', {}), ('extra', {}), ('raw_data', {})]:
        data[name] = product_data(record.get(name, default))
    data['content_hash'] = digest({**data, 'media': images})
    return data, images


@transaction.atomic(using=DB)
def save_record(run_id, record):
    data, images = validate_record(record)
    # Serialize the checkpoint and respect cancellation without holding this lock across HTTP work.
    run = SupplierRecollectionRun.objects.using(DB).select_for_update().select_related('supplier').get(pk=run_id)
    if run.status != 'running' or not run.supplier.enabled or not run.supplier.terms_confirmed:
        raise ValueError('Recollection is stopped or supplier authority changed.')
    now = timezone.now()
    item, _ = SupplierRecollectionItem.objects.using(DB).get_or_create(run=run, source_key=data['source_key'],
        defaults={'external_id': data['external_id'], 'url': data['url']})
    if item.status in ('complete', 'incomplete'):
        return 'already_processed'
    retrying_failure = item.status == 'failed'
    existing=SupplierSourceProduct.objects.using(DB).select_for_update().filter(
        supplier_id=run.supplier_id,source_key=data['source_key']).first()
    conflict=bool(existing and existing.sku and data['sku'] and existing.sku.strip()!=data['sku'].strip())
    if conflict:
        product,created=existing,False
        product.extra={**product.extra,'pending_identity_review':{
            'reason':'Original supplier identifier now reports a different SKU; staff review required.',
            'run_id':str(run.pk),'received_at':now.isoformat(),'candidate':data,'media':images}}
        product.quality={**product.quality,'missing':list(dict.fromkeys([*product.quality.get('missing',[]),'identity_review']))}
        product.last_run=run;product.save(using=DB,update_fields=['extra','quality','last_run','updated_at'])
        data['quality']=product.quality
    else:
        product, created = SupplierSourceProduct.objects.using(DB).update_or_create(supplier_id=run.supplier_id,
            source_key=data['source_key'], defaults={**data, 'last_run': run, 'observed_at': now})
    for media in ([] if conflict else images):
        previous=SupplierSourceMedia.objects.using(DB).filter(product=product,media_key=media['media_key']).first()
        if previous:
            # Same original URL and variant: keep local proof/cache. A new run
            # still causes a fresh byte verification before its next publication.
            media['metadata']={**media['metadata'],**{k:v for k,v in previous.metadata.items() if k in CACHE_PROOF_FIELDS}}
        SupplierSourceMedia.objects.using(DB).update_or_create(product=product, media_key=media['media_key'],
            defaults={**media, 'last_run': run, 'last_seen_at': now})
    # Old media remain as provenance. Only last_run media belong to this current observation.
    item.source_product, item.observed_at = product, now
    item.status = 'incomplete' if data['quality']['missing'] else 'complete'
    item.attempts += 1
    item.error = ', '.join(data['quality']['missing'])
    item.save(using=DB)
    run.processed += 0 if retrying_failure else 1
    if retrying_failure:
        run.counts = {**run.counts, 'failed': max(0, run.counts.get('failed', 0) - 1)}
    run.counts = {**run.counts, item.status: run.counts.get(item.status, 0) + 1,
                  'new' if created else 'refreshed': run.counts.get('new' if created else 'refreshed', 0) + 1}
    run.activity = f'{run.processed} fresh source products saved; {run.counts.get("incomplete", 0)} missing required content'
    run.discovered = max(run.discovered, run.processed)
    run.checkpoint = {'last_source_id': data['external_id'], 'observed_at': now.isoformat()}
    run.save(using=DB, update_fields=['processed', 'discovered', 'counts', 'activity', 'checkpoint', 'updated_at'])
    return item.status


@transaction.atomic(using=DB)
def save_failure(run_id, record):
    run = SupplierRecollectionRun.objects.using(DB).select_for_update().get(pk=run_id)
    if run.status != 'running':
        raise ValueError('Recollection is stopped.')
    key = source_key(record['external_id'], record.get('vendor_id', ''), record.get('warehouse_id', ''))
    item, _ = SupplierRecollectionItem.objects.using(DB).get_or_create(run=run, source_key=key,
        defaults={'external_id': str(record['external_id']), 'url': reference_url(record['url'])})
    if item.status in ('complete', 'incomplete'):
        return
    if item.status != 'failed':
        run.processed += 1
        run.counts = {**run.counts, 'failed': run.counts.get('failed', 0) + 1}
    item.status, item.error = 'failed', str(record['_error'])[:500]
    item.attempts += 1
    item.save(using=DB)
    run.discovered = max(run.discovered, run.processed)
    run.activity = f'{run.processed} checked; failed product is recorded separately and collection continues'
    run.save(using=DB)


@transaction.atomic(using=DB)
def apply_missing_content(source_product_id):
    """Exact source references only. Fill missing content; never replace edited text, prices or orders."""
    from django.db.models import Q
    from .models import SupplierOffer, Product, ProductImage
    from lxml import html
    source = SupplierSourceProduct.objects.using(DB).get(pk=source_product_id)
    current_images = source.media.filter(last_run_id=source.last_run_id, kind='image', role__in=('main', 'gallery'), variant_id='').order_by('position', 'pk')
    images = list(current_images)
    # A source identifier is only compared within the same supplier. Canonical URL
    # matching additionally supports old slug-derived IDs without title-only merging.
    offers = SupplierOffer.objects.using(DB).select_for_update().filter(supplier_id=source.supplier_id).filter(
        Q(external_id=source.external_id) | Q(url=source.url)).exclude(state='excluded')
    changes = {'linked_offers': 0, 'images_added': 0, 'descriptions_added': 0}
    for offer in offers:
        offer.source_product = source
        update_fields = ['source_product', 'updated_at']
        if images:
            offer.preview_images = list(dict.fromkeys(m.original_url for m in images))
            update_fields.append('preview_images')
        offer.save(using=DB, update_fields=update_fields)
        changes['linked_offers'] += 1
        if not offer.imported_product_id:
            continue
        product = Product.objects.using(DB).select_for_update().get(pk=offer.imported_product_id)
        if not product.description.strip() and source.description.strip():
            # Preserve full original HTML in source storage; publish text, not source scripts/forms.
            try:
                node = html.fragment_fromstring(source.description, create_parent='div')
                for element in node.xpath('.//script|.//style|.//form|.//input|.//iframe'):
                    element.drop_tree()
                # Plain text is safe in every consuming renderer and doesn't alter original source data.
                description = node.text_content().strip()
            except (ValueError, TypeError):
                description = source.description
            Product.objects.using(DB).filter(pk=product.pk, description=product.description).update(description=description)
            changes['descriptions_added'] += 1
        existing = set(ProductImage.objects.using(DB).filter(product_id=product.pk).values_list('url', flat=True))
        position = (ProductImage.objects.using(DB).filter(product_id=product.pk).order_by('-position').values_list('position', flat=True).first() or 0) + 1
        for image in images:
            if image.original_url in existing or len(image.original_url) > 1000:
                continue
            ProductImage.objects.using(DB).create(product=product, source_media=image, url=image.original_url,
                alt_text=source.title[:255], position=position)
            existing.add(image.original_url)
            position += 1
            changes['images_added'] += 1
    return changes
