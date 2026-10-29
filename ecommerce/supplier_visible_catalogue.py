"""Browser-rendered catalogue verification; never orders or hidden API discovery."""
import re
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from urllib.parse import urlsplit,urlunsplit,parse_qs
from django.db import transaction,close_old_connections
from django.db.models import Q
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select

from .models import SupplierSourceProduct,SupplierSourceMedia,SupplierJob,SupplierRecollectionRun
from .supplier_browser import BrowserCollector,CollectionStopped,CollectionLimitReached,amount
from .catalog_equivalents import normalized
from .supplier_source_parsers import html_product

DB='ecommerce'
QUOTE_LABELS={'your wholesale price','আপনার পাইকারি মূল্য','wholesale price','reseller price','dropshipper price','পাইকারি মূল্য'}


def canonical_url(url):
    p=urlsplit(url or '')
    return urlunsplit((p.scheme,p.netloc.removeprefix('www.'),p.path.rstrip('/'),p.query,''))


def source_for_card(supplier_id,item):
    """Exact supplier reference, or unique title PLUS the same source photo."""
    qs=SupplierSourceProduct.objects.using(DB).filter(supplier_id=supplier_id)
    url=item.get('url') or ''
    ident=str(item.get('id') or '')
    exact=list(qs.filter(Q(url=url)|Q(external_id=ident))[:3]) if url or ident else []
    exact=[s for s in exact if canonical_url(s.url)==canonical_url(url) or (ident and s.external_id==ident)]
    if len(exact)==1:return exact[0]
    # Canonical URL may differ only by www or a trailing slash.
    suffix=urlsplit(url).path.rstrip('/')
    if suffix and not urlsplit(url).fragment:
        candidates=[s for s in qs.filter(url__contains=suffix)[:20] if canonical_url(s.url)==canonical_url(url)]
        if len(candidates)==1:return candidates[0]
    image=item.get('image')
    if image:
        parts=urlsplit(image)
        if parts.path=='/_next/image':image=parse_qs(parts.query).get('url',[image])[0]
        candidates=list(qs.filter(media__original_url=image,title=item.get('title','')).distinct()[:3])
        if len(candidates)==1:return candidates[0]
    return None


def labelled_card_quote(item):
    if normalized(item.get('price_label')) not in QUOTE_LABELS:return None
    parsed=amount(item.get('price'))
    return parsed if parsed is not None and Decimal(parsed)>0 else None


def visible_labelled_price(text,label):
    matches=re.findall(re.escape(label)+r'\s*[:ঃ：]?\s*(?:৳|Tk\.?|BDT)?\s*([০-৯\d,.]+)',text,re.I)
    values={amount(value) for value in matches}
    values.discard(None)
    return next(iter(values)) if len(values)==1 and Decimal(next(iter(values)))>0 else None


def visible_stock(text):
    negative=bool(re.search(r'out of stock|স্টক\s*[:ঃ]\s*নেই|স্টকে নেই',text,re.I))
    positive=bool(re.search(r'\bin stock\b|স্টক\s*[:ঃ]\s*আছে|স্টকে আছে',text,re.I))
    quantity=re.search(r'স্টক\s*[:ঃ]\s*([০-৯\d,]+)',text)
    qty=int(quantity.group(1).replace(',','')) if quantity else None
    if negative and positive:return 'unconfirmed',None
    if negative or qty==0:return 'out_of_stock',0
    if positive or (qty is not None and qty>0):return 'in_stock',qty
    return 'unconfirmed',None


@transaction.atomic(using=DB)
def record_browser_observation(source_id,proof):
    source=SupplierSourceProduct.objects.using(DB).select_for_update().get(pk=source_id)
    old=source.extra.get('browser_verification') or {}
    if old.get('checked_at','')>proof['checked_at']:return
    source.extra={**source.extra,'browser_preferred':True,'browser_verification':proof}
    fields=['extra','prices','updated_at']
    if proof['state'] in ('verified','unavailable'):
        source.stock={**source.stock,'status':proof['stock_status']}
        if proof.get('quantity_verified'):
            source.stock['quantity']=proof.get('quantity')
        fields.append('stock')
    if proof.get('buying_price'):
        source.prices={**source.prices,'browser_buying_price':{'amount':proof['buying_price'],
            'currency':'BDT','source_label':proof.get('price_label'),'source_url':proof['product_url']}}
    if proof.get('packaging_cost') is not None:
        source.prices={**source.prices,'packagingCost':{'amount':proof['packaging_cost'],'currency':'BDT','source_label':'Visible order-form packaging cost'}}
    source.save(using=DB,update_fields=fields)
    if proof['state'] in ('verified','unavailable'):
        from .supplier_source_repair import restore_observations
        from .supplier_source_publish import refresh_listing_stock
        restore_observations(source.pk)
        for offer in source.linked_offers.exclude(state='excluded'):
            if offer.imported_product_id:refresh_listing_stock(offer)


class VisibleCatalogueCollector(BrowserCollector):
    """Reuse normal sign-in/pagination; replace lightweight identity creation.

    Already collected rich source records remain intact. Unmapped visible cards
    are logged for a mapper review, never turned into duplicate or fake offers.
    """
    def resellkori(self):
        if not getattr(self,'verify_unmapped',False):
            return super().resellkori()
        from .models import SupplierOffer
        offers=SupplierOffer.objects.using(DB).filter(
            supplier=self.job.supplier,source_product__isnull=True).order_by('pk').values(
                'pk','external_id','title','url')
        window=getattr(self,'verify_unmapped_window',None)
        if window:
            offers=offers.filter(created_at__gte=window[0],created_at__lte=window[1])
        total=offers.count()
        self.job.total=total
        self.job.save(using=DB,update_fields=['total','updated_at'])
        for offer in offers.iterator(chunk_size=100):
            self.check()
            url=offer['url']
            if not url:
                self.counts['invalid_skipped']+=1
                continue
            item={'id':offer['external_id'],'title':offer['title'],'url':url}
            self.capture([item],url)

    def source_for_visible_card(self,item):
        # One bounded projection per supplier avoids a table scan for every
        # card in a vendor/category page with hundreds of visible products.
        if not hasattr(self,'_source_index'):
            urls,identities,photos=defaultdict(set),defaultdict(set),defaultdict(set)
            titles={}
            for pk,url,external_id,title in SupplierSourceProduct.objects.using(DB).filter(
                    supplier_id=self.job.supplier_id).values_list('pk','url','external_id','title').iterator(chunk_size=1000):
                titles[pk]=normalized(title)
                if url:urls[canonical_url(url)].add(pk)
                if external_id:identities[str(external_id)].add(pk)
            for pk,url in SupplierSourceMedia.objects.using(DB).filter(
                    product__supplier_id=self.job.supplier_id,kind='image').values_list(
                        'product_id','original_url').iterator(chunk_size=1000):
                if pk in titles and url:photos[(titles[pk],url)].add(pk)
            self._source_index=(urls,identities,photos)
        urls,identities,photos=self._source_index
        url=item.get('url') or ''
        ident=str(item.get('id') or '')
        candidates=urls.get(canonical_url(url),set()) if url else set()
        if not candidates and ident:candidates=identities.get(ident,set())
        if not candidates and item.get('image'):
            picture=item['image'];parts=urlsplit(picture)
            if parts.path=='/_next/image':picture=parse_qs(parts.query).get('url',[picture])[0]
            candidates=photos.get((normalized(item.get('title')),picture),set())
        if len(candidates)!=1:return None
        return SupplierSourceProduct.objects.using(DB).get(pk=next(iter(candidates)),supplier_id=self.job.supplier_id)

    def run(self):
        super().run()
        self.job.refresh_from_db(using=DB)
        if self.job.status in ('completed','completed_with_errors'):
            SupplierJob.objects.using(DB).filter(pk=self.job.pk).update(
                activity=f'Browser verification finished: {len(self.seen)} visible cards, {self.counts["verified"]} verified, {self.counts["published"]} listing releases; no supplier orders submitted.',updated_at=timezone.now())
        run=getattr(self,'discovery_run',None)
        if run:
            run.refresh_from_db(using=DB);run.status='completed_with_errors' if run.counts.get('incomplete') or self.job.status=='failed' else 'completed'
            run.finished_at=timezone.now();run.save(using=DB)

    def capture(self,items,page,category='',vendor='not-provided'):
        self.check()
        # A supplier page can take minutes to render while the database is
        # idle. Refresh the connection before each page's catalog writes.
        close_old_connections()
        if self.pages>=self.max_pages:raise CollectionLimitReached('Browser page bound reached; partial verification only.')
        self.pages+=1
        for item in items:
            self.check()
            key=(item.get('url'),item.get('id'),item.get('title'),item.get('image'))
            if key in self.seen:continue
            self.seen.add(key)
            if item.get('access_required') or '/membership' in (item.get('url') or ''):
                self.counts['membership_held']+=1;self.counts['existing']+=1;continue
            source=self.source_for_visible_card(item)
            if not source and self.site=='business_koro':source=self.discover_business_koro(item,page)
            if not source and self.site=='resellkori':source=self.discover_resellkori(item,page)
            if not source:
                self.counts['unmapped']+=1;self.counts['failed']+=1
                self.warnings.append('Unmapped visible product: '+str(item.get('title') or '')[:150])
                continue
            proof=self.inspect_visible_product(source,item,page)
            close_old_connections()
            proof['checked_at']=timezone.now().isoformat()
            if proof.get('buying_price'):
                previous=list(source.linked_offers.exclude(source_price=None).values_list('source_price',flat=True))
                proof['different_from_saved_buying_price']=any(p!=Decimal(proof['buying_price']) for p in previous)
                if proof['different_from_saved_buying_price']:self.counts['buying_price_changed']+=1
            from .management.commands.recollect_supplier_catalogue import database_retry
            database_retry(lambda:record_browser_observation(source.pk,proof))
            self.counts[proof['state']]+=1;self.counts['existing']+=1
            if proof['state']=='verified':
                try:
                    from .source_media_repair import repair_media_membership
                    repair_media_membership(list(source.media.values_list('pk',flat=True)),apply=True)
                    from .supplier_source_publish import publish_source
                    self.counts.update(publish_source(source.pk))
                except (ValueError,OSError) as exc:
                    self.counts['publication_review']+=1
                    self.warnings.append(f'Source {source.pk}: {str(exc)[:160]}')
        self.checkpoint(page,f'Browser catalogue: {len(self.seen)} visible products; {self.counts["verified"]} verified, {self.counts["needs_review"]} need review')

    def read_business_koro_details(self,url):
        original=self.driver.current_window_handle
        try:
            self.driver.switch_to.new_window('tab');self.goto(url)
            WebDriverWait(self.driver,20).until(lambda d:d.find_elements(By.TAG_NAME,'h1') and 'প্রোডাক্টের ক্রয়মূল্য' in d.find_element(By.TAG_NAME,'body').text)
            for button in self.driver.find_elements(By.TAG_NAME,'button'):
                if button.is_displayed() and button.text.strip() in ('আরো পড়ুন','Read more','Read More'):
                    button.click();break
            details=self.dom("""const h=document.querySelector('h1'),card=h.parentElement.parentElement.parentElement;
              const description=[...card.children].find(c=>c.classList.contains('mt-4')&&!c.classList.contains('grid')&&!c.classList.contains('flex'));
              return {title:h.innerText.trim(),description:description?.innerText.replace(/(?:কম দেখুন|Show less)\\s*$/,'').trim()||'',
                header:h.parentElement.innerText,images:[...document.querySelectorAll('img')].filter(i=>i.alt===h.innerText.trim()).map(i=>({url:i.currentSrc||i.src,role:'main',alt:i.alt})),
                media_links:[...card.querySelectorAll('a[href]')].map(a=>a.href),
                controls:[...document.querySelectorAll('select')].map((s,index)=>({index,label:s.parentElement.innerText.split('\\n')[0],options:[...s.options].filter(o=>o.value&&!o.disabled).map(o=>({value:o.value,label:o.text.trim()}))}))};""")
            price=re.search(r'আপনার পাইকারি মূল্য\s*৳\s*([\d,.]+)',details['header'])
            details['buying_price']=amount(price.group(1)) if price else None
            body=self.driver.find_element(By.TAG_NAME,'body').text
            packaging=re.search(r'প্যাকেজিং খরচ\s*(?:−|-)?\s*৳\s*([\d,.]+)',body)
            details['packaging_cost']=amount(packaging.group(1)) if packaging else None
            total=re.search(r'([\d,]+)\s*স্টকে আছে',details['header'])
            details['total_quantity']=int(total.group(1).replace(',','')) if total else None
            controls=[c for c in details['controls'] if re.search(r'color|colour|কালার|রং|size|সাইজ',c['label'],re.I)]
            if len(controls)>2:raise CollectionStopped('More than two dependent product choices require a reviewed browser mapper.')
            variants=[]
            def current_cost():
                body=self.driver.find_element(By.TAG_NAME,'body').text
                found=re.search(r'প্রোডাক্টের ক্রয়মূল্য\s*৳\s*([\d,.]+)',body)
                return amount(found.group(1)) if found else details['buying_price']
            if controls:
                first=controls[0];first_name='size' if re.search(r'size|সাইজ',first['label'],re.I) else 'color'
                for option in first['options']:
                    Select(self.driver.find_elements(By.TAG_NAME,'select')[first['index']]).select_by_value(option['value'])
                    # Read dependent choices AFTER selecting this actual parent.
                    # Never manufacture a colour x size cross product.
                    second=self.dom("""return [...document.querySelectorAll('select')].map((s,index)=>({index,label:s.parentElement.innerText.split('\\n')[0],options:[...s.options].filter(o=>o.value&&!o.disabled).map(o=>({value:o.value,label:o.text.trim()}))}));""")
                    second=[c for c in second if c['index']!=first['index'] and re.search(r'color|colour|কালার|রং|size|সাইজ',c['label'],re.I)]
                    choices=second[0]['options'] if second else [None]
                    for choice in choices:
                        spec={first_name:option['label']}
                        if choice:
                            Select(self.driver.find_elements(By.TAG_NAME,'select')[second[0]['index']]).select_by_value(choice['value'])
                            spec['size' if first_name=='color' else 'color']=choice['label']
                        variant_id='browser-spec-'+hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:32]
                        option_text=self.dom('return document.querySelector("select").parentElement.parentElement.innerText')
                        unavailable=bool(re.search(r'out of stock|স্টক নেই|স্টকে নেই|স্টক শেষ',option_text,re.I))
                        pictures=self.dom("return [...document.querySelectorAll('img')].filter(i=>i.alt===document.querySelector('h1').innerText.trim()).map(i=>i.currentSrc||i.src)")
                        variants.append({'id':variant_id,'spec':spec,'buying_price':current_cost(),
                            'quantity':0 if unavailable else None,'image_urls':pictures})
                        for picture in pictures:
                            if picture not in {m['url'] for m in details['images']}:
                                details['images'].append({'url':picture,'role':'variant','variant_id':variant_id,'alt':details['title']})
                        if len(variants)>200:raise CollectionStopped('Visible variant count exceeds the reviewed combination bound.')
            details['visible_variants']=variants
            return details
        finally:
            if self.driver.current_window_handle!=original:self.driver.close()
            self.driver.switch_to.window(original)

    def discover_business_koro(self,item,page):
        # New identities originate in actual visible links, never hidden IDs.
        details=self.read_business_koro_details(item['url'])
        if not details['buying_price'] or details['total_quantity']==0:return None
        from .supplier_recollection import save_record,source_key,MAPPING_VERSION
        if not getattr(self,'discovery_run',None):
            self.discovery_run=SupplierRecollectionRun.objects.using(DB).create(supplier=self.job.supplier,
                mode='inspect',status='running',mapping_version=MAPPING_VERSION,
                coverage={'method':'rendered browser product pages','new_sources_only':True,'browser_job_id':str(self.job.pk)})
        external='browser-url-'+hashlib.sha256(canonical_url(item['url']).encode()).hexdigest()[:48]
        proof={'method':'rendered_browser_dom','state':'verified','checked_at':timezone.now().isoformat(),
            'buying_price':details['buying_price'],'price_label':'আপনার পাইকারি মূল্য',
            'product_url':item['url'],'catalogue_url':page,'stock_status':'in_stock',
            'quantity':details['total_quantity'] if not details['visible_variants'] else None,
            'quantity_verified':not bool(details['visible_variants']) and details['total_quantity'] is not None,
            'visible_variants':details['visible_variants'],'packaging_cost':details.get('packaging_cost')}
        record={'external_id':external,'url':item['url'],'title':details['title'],'description':details['description'],
            'media':details['images'],'prices':{'browser_buying_price':{'amount':details['buying_price'],'currency':'BDT'}},
            'stock':{'status':'in_stock','quantity':details['total_quantity']},'variants':details['visible_variants'],
            'extra':{'identity_origin':'browser_url','provider_variant_ids_available':False,'browser_preferred':True,
                'browser_verification':proof,'supplier_media_links':details['media_links']},'raw_data':{'browser_product':details}}
        if details.get('packaging_cost') is not None:record['prices']['packagingCost']={'amount':details['packaging_cost'],'currency':'BDT'}
        from .models import SupplierOffer
        excluded=SupplierOffer.objects.using(DB).filter(supplier=self.job.supplier).filter(
            Q(url=item['url'])|Q(title=details['title'])).filter(Q(state='excluded')|~Q(excluded_reason='')).exists()
        if excluded:record['extra']['manual_exclusion_review']=True
        save_record(self.discovery_run.pk,record)
        self.counts['new_browser_sources']+=1
        source=SupplierSourceProduct.objects.using(DB).get(supplier=self.job.supplier,source_key=source_key(external))
        if not hasattr(self,'fresh_discoveries'):self.fresh_discoveries={}
        self.fresh_discoveries[source.pk]=proof
        return source

    def discover_resellkori(self,item,page):
        """Build a rich source record from this exact signed-in product page."""
        url=item.get('url') or ''
        if not url:
            return None
        original=self.driver.current_window_handle
        try:
            self.driver.switch_to.new_window('tab');self.goto(url)
            if canonical_url(self.driver.current_url)!=canonical_url(url):
                self.warnings.append('ResellKori redirected an unmapped product page; held for review.')
                return None
            WebDriverWait(self.driver,20).until(lambda d:d.find_elements(By.CSS_SELECTOR,'.single-product-content .summary'))
            external=str(item.get('id') or 'browser-url-'+hashlib.sha256(canonical_url(url).encode()).hexdigest()[:48])
            record=html_product('resellkori',self.driver.current_url,self.driver.page_source,
                external_id=external,title=item.get('title') or '')
            summary=self.driver.find_element(By.CSS_SELECTOR,'.single-product-content .summary').text
            stock_status,quantity=visible_stock(summary)
            record['stock']={**record.get('stock',{}),'status':stock_status}
            if quantity is not None:
                record['stock']['quantity']=quantity
            if not record.get('media') or not record.get('description'):
                self.warnings.append('ResellKori source page lacks a verified gallery or description; held for review.')
                return None
            record['extra']={**record.get('extra',{}),'identity_origin':'browser_url',
                'browser_preferred':True,'catalogue_url':page}
            if not getattr(self,'discovery_run',None):
                from .supplier_recollection import MAPPING_VERSION
                self.discovery_run=SupplierRecollectionRun.objects.using(DB).create(
                    supplier=self.job.supplier,mode='inspect',status='running',mapping_version=MAPPING_VERSION,
                    coverage={'method':'signed-in rendered ResellKori pages','new_sources_only':True,
                              'browser_job_id':str(self.job.pk)})
            from .supplier_recollection import save_record,source_key
            save_record(self.discovery_run.pk,record)
            source=SupplierSourceProduct.objects.using(DB).get(
                supplier=self.job.supplier,source_key=source_key(external))
            self.counts['new_browser_sources']+=1
            return source
        except ValueError as exc:
            self.warnings.append('ResellKori product needs mapper review: '+str(exc)[:120])
            return None
        finally:
            if self.driver.current_window_handle!=original:self.driver.close()
            self.driver.switch_to.window(original)

    def inspect_visible_product(self,source,item,page):
        proof={'method':'rendered_browser_dom','checked_at':timezone.now().isoformat(),
            'catalogue_url':page,'product_url':source.url,'state':'needs_review','buying_price':None,
            'quantity':None,'quantity_verified':False,'stock_status':'unconfirmed',
            'scope':'Visible catalogue and own product page only; no supplier order submitted.'}
        if self.site=='business_koro':
            fresh=getattr(self,'fresh_discoveries',{}).pop(source.pk,None)
            if fresh:return fresh
            if source.extra.get('identity_origin')=='browser_url':
                details=self.read_business_koro_details(item['url'])
                proof.update(buying_price=details['buying_price'],price_label='আপনার পাইকারি মূল্য',
                    visible_variants=details['visible_variants'],stock_status='in_stock',
                    packaging_cost=details.get('packaging_cost'),
                    quantity=details['total_quantity'] if not details['visible_variants'] else None,
                    quantity_verified=not bool(details['visible_variants']) and details['total_quantity'] is not None)
                proof['state']='unavailable' if details['total_quantity']==0 else 'verified' if details['buying_price'] else 'needs_review'
                return proof
            proof['scope']='Visible signed-in buying-price/stock card; existing full descriptions and structured options retained separately.'
            proof['buying_price']=labelled_card_quote(item);proof['price_label']=item.get('price_label')
            stock=normalized(item.get('stock_text'))
            if stock.startswith(('out of stock','স্টক নেই')):proof.update(state='unavailable',stock_status='out_of_stock')
            elif stock.startswith(('in stock','low stock')):
                proof['stock_status']='in_stock'
                low=re.search(r'low stock\s*[·:]\s*(\d+)',stock)
                if low:proof.update(quantity=int(low.group(1)),quantity_verified=True)
                if proof['buying_price']:proof['state']='verified'
            return proof
        if self.site in ('shopbase','dropbazar','dropify','resellkori'):
            original=self.driver.current_window_handle
            try:
                self.driver.switch_to.new_window('tab');self.goto(source.url)
                if canonical_url(self.driver.current_url)!=canonical_url(source.url):
                    proof['reason']='Supplier redirected the product; account/access review required.';return proof
                WebDriverWait(self.driver,20).until(lambda d:d.find_element(By.TAG_NAME,'body').text.strip())
                record=html_product(self.site,self.driver.current_url,self.driver.page_source,
                    external_id=source.external_id,title=source.title)
                field={'shopbase':'reseller_price','dropbazar':'reseller_price','dropify':'wholesale','resellkori':'reseller'}[self.site]
                proof['price_label']=(record.get('prices',{}).get(field) or {}).get('source_label') or field
                selector={'shopbase':'.product-details-page','dropbazar':'body','dropify':'.pd-info-col','resellkori':'.single-product-content .summary'}[self.site]
                scopes=[e for e in self.driver.find_elements(By.CSS_SELECTOR,selector) if e.is_displayed()]
                text=scopes[0].text if len(scopes)==1 else self.driver.find_element(By.TAG_NAME,'body').text
                # Rendered text, not hidden inputs, script payloads or CSS-hidden
                # prices, must corroborate the labelled product-only buying cost.
                price=visible_labelled_price(text,proof['price_label'])
                if price is not None and Decimal(price)>0:proof['buying_price']=str(price)
                status,quantity=visible_stock(text)
                if status=='out_of_stock':proof.update(state='unavailable',stock_status='out_of_stock')
                elif status=='in_stock':
                    proof['stock_status']='in_stock'
                    if quantity is not None:proof.update(quantity=quantity,quantity_verified=True)
                    if proof['buying_price']:proof['state']='verified'
                return proof
            finally:
                if self.driver.current_window_handle!=original:self.driver.close()
                self.driver.switch_to.window(original)
        # These app libraries expose selling ranges, not an unambiguous buying
        # quote on their cards. Do not turn their minimum/suggested prices into cost.
        proof['reason']='Visible card does not expose an unambiguous buying-price and stock label. Exact detail/variant review required.'
        return proof
