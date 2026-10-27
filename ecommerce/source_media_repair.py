"""Repair current-gallery membership using original source URL evidence only."""
import re
from html import unescape
from django.db.models import F
from django.utils import timezone
from .models import SupplierSourceProduct,SupplierSourceMedia

DB='ecommerce'


def original_urls(value):
    found=set()
    def visit(item):
        if isinstance(item,dict):
            for child in item.values():visit(child)
        elif isinstance(item,list):
            for child in item:visit(child)
        elif isinstance(item,str):
            found.update(re.findall(r'https://[^\s<>"\'\\]+',unescape(item)))
    visit(value)
    return found


def repair_media_membership(ids=None,apply=False):
    qs=SupplierSourceMedia.objects.using(DB).filter(kind='image',variant_id='',role__in=('main','gallery')).exclude(last_run_id=F('product__last_run_id'))
    if ids is not None:qs=qs.filter(pk__in=ids)
    counts={'mismatched':0,'proven_current_reference':0,'unproven_held':0,'repaired':0}
    after=0
    while True:
        rows=list(qs.filter(pk__gt=after).order_by('pk')[:200])
        if not rows:break
        sources={s.pk:s for s in SupplierSourceProduct.objects.using(DB).filter(pk__in={m.product_id for m in rows}).only('pk','raw_data','last_run','observed_at')}
        urls={pk:original_urls(s.raw_data) for pk,s in sources.items()}
        changed=[]
        for media in rows:
            counts['mismatched']+=1;source=sources[media.product_id]
            if media.original_url not in urls[source.pk]:counts['unproven_held']+=1;continue
            counts['proven_current_reference']+=1
            media.last_run_id=source.last_run_id
            media.last_seen_at=max(media.last_seen_at,source.observed_at)
            media.metadata={**media.metadata,'reference_confirmed_run_id':str(source.last_run_id),
                'reference_confirmed_at':source.observed_at.isoformat(),
                'reference_confirmation_kind':'original URL present in current source product payload'}
            media.updated_at=timezone.now();changed.append(media)
        if apply and changed:
            from .management.commands.recollect_supplier_catalogue import database_retry
            database_retry(lambda:SupplierSourceMedia.objects.using(DB).bulk_update(changed,
                ['last_run','last_seen_at','metadata','updated_at'],batch_size=100))
            counts['repaired']+=len(changed)
        after=rows[-1].pk
    return counts
