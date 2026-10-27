"""Resolve synthetic browser-card IDs only with independent parent-product proof."""
import json,re,unicodedata
from collections import defaultdict,Counter
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from ecommerce.models import SupplierSourceProduct,SupplierOffer,Product,SupplierSourceMedia
from ecommerce.supplier_service import audit


def title(value):return ' '.join(unicodedata.normalize('NFKC',str(value or '')).casefold().split())
def image_key(value):
    if not isinstance(value,str) or re.search(r'logo|placeholder|cheradip',value,re.I):return ''
    u=urlsplit(value)
    return urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path,urlencode([(k,v) for k,v in parse_qsl(u.query) if k not in ('width','height','w','h','quality','format')]),''))


class Command(BaseCommand):
    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--report',required=True)

    def handle(self,*args,**options):
        index=defaultdict(list)
        for source in SupplierSourceProduct.objects.using('ecommerce').only('id','supplier_id','title','sku','url','variants','vendor_id','warehouse_id'):
            index[source.supplier_id,title(source.title)].append(source)
        media=defaultdict(set)
        for source_id,original,stored in SupplierSourceMedia.objects.using('ecommerce').filter(kind='image',role__in=('main','gallery','variant')).values_list('product_id','original_url','stored_url').iterator(chunk_size=1000):
            media[source_id].update(filter(None,(image_key(original),image_key(stored))))
        counts,results=Counter(),[]
        # Blank exclusion is required; excluded offers remain untouched.
        qs=SupplierOffer.objects.using('ecommerce').filter(source_product=None,excluded_reason='').exclude(state='excluded').order_by('pk')
        for offer in qs.iterator(chunk_size=100):
            candidates=index[offer.supplier_id,title(offer.title)]
            if len(candidates)!=1:counts['ambiguous_or_missing_title']+=1;continue
            source=candidates[0]
            if any(a and a!='not-provided' and b and a!=b for a,b in ((offer.vendor_id,source.vendor_id),(offer.warehouse_id,source.warehouse_id))):
                counts['vendor_conflict']+=1;continue
            sku=str((offer.identity or {}).get('sku') or (offer.identity or {}).get('product_code') or '').strip()
            if sku and source.sku and sku.casefold()!=source.sku.casefold():counts['sku_conflict']+=1;continue
            same_sku=bool(sku and source.sku and sku.casefold()==source.sku.casefold())
            images={image_key(v) for v in (offer.preview_images or [])}
            images.discard('')
            common=images & media[source.pk]
            if not same_sku and not common:counts['no_independent_identity_proof']+=1;continue
            result={'offer_id':offer.pk,'source_id':source.pk,'proof':'unique exact title and '+('SKU' if same_sku else 'original product image'),'original_url':offer.url,'source_url':source.url}
            if options['apply']:
                with transaction.atomic(using='ecommerce'):
                    current=SupplierOffer.objects.using('ecommerce').select_for_update().get(pk=offer.pk)
                    if current.source_product_id:continue
                    current.source_product=source;current.url=source.url
                    current.save(using='ecommerce',update_fields=['source_product','url','updated_at'])
                    canonical=SupplierOffer.objects.using('ecommerce').filter(source_product=source,variant_id='',imported_product__isnull=False).exclude(pk=current.pk).first()
                    if canonical and current.imported_product_id and not source.variants and re.fullmatch(r'catalogue-type-\d*|',current.variant_id):
                        product=Product.objects.using('ecommerce').get(pk=current.imported_product_id)
                        Product.objects.using('ecommerce').filter(pk=product.pk).update(status='archived',
                            attributes={**product.attributes,'_catalog_duplicate_of_slug':canonical.imported_product.slug},updated_at=timezone.now())
                        result['canonical_product_id']=canonical.imported_product_id
                    audit('legacy_source_reference_repaired',supplier=current.supplier,offer=current,source_id=source.pk,proof=result['proof'],original_url=result['original_url'])
            counts['matched']+=1;results.append(result)
        Path(options['report']).write_text(json.dumps({'apply':options['apply'],'counts':counts,'matches':results},ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(counts))
