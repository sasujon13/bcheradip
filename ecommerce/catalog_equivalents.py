"""Conservative cross-supplier catalogue consolidation, never order rewriting."""
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from .models import SupplierSourceProduct, SupplierSourceMedia, SupplierOffer, Product
from .supplier_recollection import description_text
from .supplier_service import audit

DB='ecommerce'


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC',str(value or '')).casefold().split())


def exact_content_key(source,photo_sha):
    """Require full matching source content AND a verified identical main photo.

    Title-only, image-only, missing content and unresolved variant mappings are
    candidates for staff review, never proof that two sale units are equivalent.
    Supplier prices/stock/IDs are deliberately outside product identity.
    """
    description=normalized(description_text(source.description or source.short_description))
    if (len(description)<80 or source.quality.get('missing') or source.variants or
        source.extra.get('variant_inputs') or not re.fullmatch(r'[a-f0-9]{64}',photo_sha or '')):
        return None
    payload={'title':normalized(source.title),'description':description,
        'specifications':source.specifications,'features':source.features,'photo_sha256':photo_sha}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def audit_equivalents():
    sources=list(SupplierSourceProduct.objects.using(DB).defer('raw_data').all())
    photos={}
    for media in SupplierSourceMedia.objects.using(DB).filter(kind='image',role__in=('main','gallery'),
            metadata__verified_image=True).order_by('position','pk').values('product_id','last_run_id','metadata'):
        key=(media['product_id'],media['last_run_id'])
        sha=media['metadata'].get('sha256')
        if key not in photos and re.fullmatch(r'[a-f0-9]{64}',sha or ''):photos[key]=sha
    titles,exact=defaultdict(list),defaultdict(list)
    for source in sources:
        titles[normalized(source.title)].append(source)
        key=exact_content_key(source,photos.get((source.pk,source.last_run_id)))
        if key:exact[key].append(source)
    candidates=[{'title':rows[0].title,'source_ids':[s.pk for s in rows],
        'supplier_ids':sorted({s.supplier_id for s in rows})} for rows in titles.values()
        if len({s.supplier_id for s in rows})>1]
    groups=[{'key':key,'title':rows[0].title,'source_ids':[s.pk for s in rows],
        'supplier_ids':sorted({s.supplier_id for s in rows}),
        'evidence':'Identical full description, specifications, features and verified main-image bytes; no unresolved structured options.'}
        for key,rows in exact.items() if len({s.supplier_id for s in rows})>1]
    return {'at':timezone.now().isoformat(),'source_records_checked':len(sources),
        'same_title_review_groups':candidates,'exact_content_groups':groups}


@transaction.atomic(using=DB)
def consolidate_group(group):
    """Keep the cheapest currently purchasable offer; preserve all source history.

    No product/customer order references are reassigned and no records deleted.
    Existing orders continue to refer to their original source and accepted price.
    """
    from .manual_catalogue import purchasable_offers
    offers=list(SupplierOffer.objects.using(DB).select_for_update().filter(
        source_product_id__in=group['source_ids']).exclude(state='excluded').select_related('supplier'))
    def choices(offer):
        spec=offer.identity.get('specifications') or {}
        selected={key:normalized(spec.get(key)) for key in ('color','colour','size','capacity','pack_count') if spec.get(key)}
        variant=normalized(offer.identity.get('variant'))
        if variant and variant not in ('default','standard'):selected['variant']=variant
        return json.dumps(selected,sort_keys=True)
    if len({choices(o) for o in offers})>1:
        return {'state':'needs_review','reason':'Offer-level size/color/pack choices differ or are not confirmed on both sources.'}
    eligible_ids=set(purchasable_offers(include_equivalent_alternatives=True).filter(pk__in=[o.pk for o in offers]).order_by().values_list('pk',flat=True))
    eligible=[o for o in offers if o.pk in eligible_ids and o.imported_product_id and
        o.currency=='BDT' and o.source_price is not None and Decimal(o.source_price)>0]
    if not eligible:return {'state':'needs_review','reason':'No currently purchasable, positively priced exact offer.'}
    winner=min(eligible,key=lambda o:(o.source_price,o.pk))
    product=Product.objects.using(DB).select_for_update().get(pk=winner.imported_product_id)
    # Do not revive a staff archive or silently follow a navigation-duplicate chain.
    retained_alternative=product.attributes.get('_supplier_equivalence',{})
    can_restore=retained_alternative.get('group')==group['key'] and retained_alternative.get('previous_status')=='active'
    if (product.status!='active' or product.attributes.get('_catalog_duplicate_of_slug')) and not can_restore:
        return {'state':'needs_review','reason':'The lowest-price listing is not an active canonical listing.'}
    if can_restore:
        attrs=dict(product.attributes);attrs.pop('_catalog_duplicate_of_slug',None);attrs.pop('_supplier_equivalence',None)
        Product.objects.using(DB).filter(pk=product.pk).update(status='active',attributes=attrs,updated_at=timezone.now())
    archived=[]
    for offer in offers:
        if offer.pk==winner.pk or not offer.imported_product_id:continue
        old=Product.objects.using(DB).select_for_update().get(pk=offer.imported_product_id)
        prior=old.attributes.get('_catalog_duplicate_of_slug')
        previous=old.attributes.get('_supplier_equivalence',{})
        if prior and prior!=product.slug and previous.get('group')!=group['key']:continue
        if (prior==product.slug and old.status=='archived' and previous.get('group')==group['key'] and
                previous.get('winning_buying_price')==str(winner.source_price)):continue
        info={'group':group['key'],'canonical_slug':product.slug,'reason':group['evidence'],
            'buying_price':str(offer.source_price) if offer.source_price is not None else None,
            'winning_buying_price':str(winner.source_price),'checked_at':timezone.now().isoformat(),
            'previous_status':old.attributes.get('_supplier_equivalence',{}).get('previous_status',old.status)}
        attrs={**old.attributes,'_catalog_duplicate_of_slug':product.slug,'_supplier_equivalence':info}
        Product.objects.using(DB).filter(pk=old.pk).update(status='archived',attributes=attrs,updated_at=timezone.now())
        archived.append(old.slug)
    if archived:audit('exact_supplier_duplicates_consolidated',supplier=winner.supplier,offer=winner,
        group=group['key'],canonical_slug=product.slug,buying_price=str(winner.source_price),
        archived_slugs=archived,evidence=group['evidence'],orders_changed=False)
    return {'state':'consolidated' if archived else 'already_single','canonical_slug':product.slug,
        'winning_buying_price':str(winner.source_price),'archived_slugs':archived}
