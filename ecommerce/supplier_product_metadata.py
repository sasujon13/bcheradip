"""Preserve product-only HTML metadata without persisting application/auth scripts.

Structured/public retail prices are evidence, never a replacement buying price.
Ambiguous images remain metadata rather than being promoted to an own gallery.
"""
import json
import re
from urllib.parse import urljoin,urlsplit
from lxml import html


def key(value):
    return ' '.join(str(value or '').casefold().split())


def page_metadata(doc,url,title):
    metas={}
    for n in doc.xpath('//head/meta[@content]'):
        name=n.get('property') or n.get('name') or n.get('itemprop') or ''
        if name.startswith(('og:','product:','twitter:')) or name in ('description','keywords'):
            metas.setdefault(name,[]).append(n.get('content'))
    canonical=[urljoin(url,n) for n in doc.xpath('//head/link[@rel="canonical"]/@href')]
    def nodes(value):
        if isinstance(value,list):
            for child in value:yield from nodes(child)
        elif isinstance(value,dict):
            types=value.get('@type',[])
            if isinstance(types,str):types=[types]
            if any(t in ('Product','ProductGroup') for t in types):yield value
            if '@graph' in value:yield from nodes(value['@graph'])
            if 'mainEntity' in value:yield from nodes(value['mainEntity'])
    products=[];invalid=0
    for script in doc.xpath('//script[@type="application/ld+json"]'):
        try:products.extend(nodes(json.loads(script.text or '')))
        except (ValueError,TypeError):invalid+=1
    own=[];unmatched=0
    paths={urlsplit(u).path.rstrip('/') for u in [url,*canonical]}
    for product in products:
        declared=product.get('url') or product.get('@id') or ''
        if not isinstance(declared,str):declared=''
        matches_url=bool(declared and urlsplit(urljoin(url,declared)).path.rstrip('/') in paths)
        if key(product.get('name'))==key(title) and (matches_url or (not declared and len(products)==1)):
            own.append(product)
        else:unmatched+=1
    breadcrumbs=[]
    for element in doc.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," breadcrumb ")]'):
        breadcrumbs.extend({'name':' '.join(a.text_content().split()),'url':urljoin(url,a.get('href'))}
                           for a in element.xpath('.//a[@href]'))
    sku=''
    for n in doc.xpath('//*[@itemprop="sku"]|//*[@id="product-code"]|//*[@id="product_code"]|//input[@name="product_code"]'):
        sku=(n.get('content') or n.get('value') or n.text_content()).strip()
        if sku:break
    if not sku:
        sku=next((str(p['sku']) for p in own if p.get('sku')), '')
    return {'meta':metas,'canonical':canonical,'structured_products':own,'breadcrumbs':breadcrumbs,
            'unmatched_structured_product_count':unmatched,'invalid_json_ld_count':invalid,'sku':sku}


def enrich_record(record,body,url):
    doc=html.fromstring(body,base_url=url)
    info=page_metadata(doc,url,record['title'])
    record.setdefault('extra',{})['html_metadata']=info
    record.setdefault('raw_data',{})['product_metadata']=info
    if not record.get('sku') and info['sku']:record['sku']=info['sku']
    if not record.get('categories'):
        record['categories']=[b for b in info['breadcrumbs'] if b['name'].casefold() not in
                              ('home','products','all products','dashboard','application','হোম') and b['url'].rstrip('/')!=url.rstrip('/')]
    for product in info['structured_products']:
        for field in ('brand','manufacturer','model','mpn','gtin','gtin13','material','color','size','weight',
                      'width','height','depth','warranty','aggregateRating','review','additionalProperty','offers','video'):
            if field in product:
                record['extra'].setdefault('structured_attributes',{})[field]=product[field]
        if product.get('additionalProperty'):
            record.setdefault('specifications',{})['structured_properties']=product['additionalProperty']
    descriptions=doc.xpath('//*[@id="home" or @id="description" or @id="descriptionCopy" or '
        'contains(concat(" ",normalize-space(@class)," ")," pd-desc-content ") or '
        'contains(concat(" ",normalize-space(@class)," ")," pdp-desc-content ")]')
    for container in descriptions:
        for image in container.xpath('.//img[@src]'):
            record.setdefault('media',[]).append({'url':urljoin(url,image.get('src')),'kind':'image',
                'role':'description','metadata':{'source_field':'original product description'}})
        for value in container.xpath('.//video/@src|.//video/source/@src|.//iframe/@src'):
            record.setdefault('media',[]).append({'url':urljoin(url,value),'kind':'video','role':'video',
                'metadata':{'source_field':'original product description video'}})
    # Body-only SKU labels must precede related-product cards; accept a dedicated
    # code element, not a random number or a supplier's organisation name.
    for element in doc.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," product-code ") or contains(concat(" ",normalize-space(@class)," ")," pd-sku ")]'):
        value=' '.join(element.text_content().split())
        match=re.search(r'\bSKU\s*:\s*([^|]+)',value,re.I)
        if not record.get('sku') and match:record['sku']=match.group(1).strip()
        category=re.search(r'\bCategory\s*:\s*([^|]+)',value,re.I)
        if not record.get('categories') and category:record['categories']=[{'name':category.group(1).strip()}]
    if not record.get('sku'):
        codes=set()
        for value in doc.xpath('//body//text()[not(ancestor::script) and not(ancestor::style)]'):
            match=re.fullmatch(r'\s*SKU\s*:\s*([\w.-]+)\s*',value,re.I)
            if match:codes.add(match.group(1))
        if len(codes)==1:record['sku']=codes.pop()
    info['sku']=record.get('sku') or info['sku']
    if record.get('extra',{}).get('features_html') and not record.get('features'):
        record['features']=[{'html':record['extra']['features_html'],'source_field':'original features section'}]
    return record
