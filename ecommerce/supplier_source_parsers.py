"""Mappings verified against original supplier samples; retail and buying prices stay distinct."""
import json
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from lxml import html


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).translate(str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')).replace(',', '')
    found = re.findall(r'\d+(?:\.\d+)?', text)
    if len(found) != 1 or re.search(r'[-−]\s*\d', text):
        return None
    try:
        number = Decimal(found[0])
        return str(number.quantize(Decimal('.01'))) if number.is_finite() and number >= 0 else None
    except InvalidOperation:
        return None


def media(url, *, role='gallery', variant_id='', alt='', **metadata):
    return {'url': url, 'role': role, 'variant_id': str(variant_id or ''), 'alt': alt or '', 'metadata': metadata}


def array(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def business_koro(product, delivery=None):
    images = array(product.get('images'))
    primary = product.get('mainImageUrl') or product.get('image')
    if primary:
        images = [primary, *images]
    image_rows = [media(x, role='main' if n == 0 else 'gallery', source_field='images') for n, x in enumerate(images) if isinstance(x, str)]
    for entry in product.get('media') or []:
        if not isinstance(entry, dict) or not entry.get('url'):
            continue
        kind = str(entry.get('type') or entry.get('kind') or '').lower()
        if kind in ('image', 'video'):
            image_rows.append({'url': entry['url'], 'role': 'gallery' if kind == 'image' else 'video', 'kind': kind, 'metadata': entry})
    variants = deepcopy(product.get('variants') or [])
    for variant in variants:
        for url in [variant.get('image'), *array(variant.get('images'))]:
            if isinstance(url, str) and url:
                image_rows.append(media(url, role='variant', variant_id=variant.get('id'), source_field='variants'))
    prices = {k: {'amount': amount(product.get(k)), 'currency': 'BDT', 'source_field': k} for k in
              ('costPrice', 'baseCost', 'suggestedPrice', 'suggestedPriceMin', 'suggestedPriceMax', 'suggestedSellPrice', 'suggestedSellPriceMin', 'suggestedSellPriceMax', 'minimumSellingPrice', 'packagingCost', 'courierCharge') if k in product}
    prices['buying_basis'] = 'Source-labelled cost/baseCost; packaging and courier are separate. Respect account locked/access flags.'
    return {'external_id': str(product['id']), 'url': 'https://www.businesskoro.com/dashboard/products/' + str(product['slug']),
        'title': product['name'], 'sku': product.get('sku', ''), 'description': product.get('description') or '',
        'short_description': product.get('shortDescription') or '', 'categories': [product['category']] if product.get('category') else [],
        'specifications': product.get('specifications') or {}, 'features': product.get('features') or [],
        'prices': prices, 'stock': {'quantity': product.get('stockQuantity'), 'in_stock': product.get('inStock')},
        'variants': variants, 'media': image_rows, 'shipping': {'deliveryCharges': delivery},
        'extra': {k: v for k, v in product.items() if k not in ('description', 'images', 'variants')}, 'raw_data': {'product': product}}


def selfshop(payload):
    p = payload['data']['product_details']
    images = [p.get('ViewProductImage'), p.get('ProductImage'), *array(p.get('PostImage'))]
    image_rows = [media(u, role='main' if n == 0 else 'gallery', source_field='ProductImage/PostImage') for n, u in enumerate(images) if isinstance(u, str) and u]
    variants = deepcopy(p.get('varients') or [])
    for variant in variants:
        if variant.get('image'):
            image_rows.append(media(variant['image'], role='variant', variant_id=variant['id'], source_field='varients.image'))
        for size in variant.get('sizes') or []:
            if size.get('image'):
                image_rows.append(media(size['image'], role='variant', variant_id=str(variant['id']) + ':' + str(size['id']), source_field='varients.sizes.image'))
    if p.get('youtube_link'):
        image_rows.append({'url':p['youtube_link'],'kind':'video','role':'video','metadata':{'source_field':'youtube_link'}})
    prices = {key: {'amount': amount(p.get(key)), 'currency': 'BDT', 'source_field': key} for key in
        ('ProductWholesalePrice', 'ProductResellerPrice', 'min_sell_price', 'ProductRegularPrice', 'ProductSalePrice', 'minimum_selling_price', 'storefront_price') if key in p}
    prices.update(pricing_locked=bool(p.get('pricing_locked')), price_tiers=p.get('price_tiers') or [],
                  buying_basis='SelfShop visible Price/storefront_price is payable buying cost; reseller/internal wholesale and minimum selling are not payable cost. Unconfirmed while pricing_locked.')
    shipping_fields = ('product_weight', 'weight', 'shipping_days', 'ex_pack', 'ex_dvc', 'extra_delivery_per_qty')
    return {'external_id': str(p['id']), 'vendor_id': str(p.get('vendor_id') or ''), 'warehouse_id': str(p.get('warehouse_id') or ''),
        'url': 'https://selfshop.com.bd/product/' + p['ProductSlug'], 'title': p['ProductName'], 'sku': p.get('ProductSku') or '',
        'short_description': p.get('ProductBreaf') or '', 'description': p.get('ProductDetails') or '',
        'categories': [p['categories']] if p.get('categories') else [], 'prices': prices,
        'stock': {k: p.get(k) for k in ('qty', 'show_stock', 'show_stock_text', 'status', 'minimum_qty')},
        'variants': variants, 'shipping': {k: p.get(k) for k in shipping_fields}, 'media': image_rows,
        'extra': {k: v for k, v in p.items() if k not in ('ProductDetails', 'ProductBreaf', 'varients', 'PostImage')},
        'raw_data': {'product_details': p, 'flash_sale': payload['data'].get('flash_sale'), 'commission_percent': payload['data'].get('commission_percent')}}


def uddoog(payload):
    data = payload.get('data', payload)
    p = data.get('product', data)
    images = [p.get('thumbnail'), *array(p.get('gallery'))]
    image_rows = [media(urljoin('https://dropshop.com.bd', u), role='main' if n == 0 else 'gallery', source_field='thumbnail/gallery', original_reference=u) for n, u in enumerate(images) if isinstance(u, str) and u]
    variants = deepcopy(p.get('variants') or [])
    for variant in variants:
        for url in [variant.get('image'), *array(variant.get('images'))]:
            if isinstance(url, str) and url:
                image_rows.append(media(urljoin('https://dropshop.com.bd',url), role='variant', variant_id=variant.get('id'), source_field='variants', original_reference=url))
    for entry in data.get('content') or []:
        if isinstance(entry, dict) and entry.get('type') == 'video' and entry.get('url'):
            image_rows.append({'url': entry['url'], 'kind': 'video', 'role': 'video', 'metadata': {'source_field': 'content'}})
    return {'external_id': str(p['id']), 'vendor_id': str(p.get('vendor_id') or ''), 'warehouse_id': str(p.get('warehouse_id') or ''),
        'url': 'https://dropshop.com.bd/products/' + p['slug'], 'title': p['name'], 'sku': p.get('sku') or '',
        'description': p.get('description') or '', 'short_description':p.get('short_description') or '',
        'categories': p.get('categories') or [], 'media': image_rows,
        'prices': {**{k: {'amount': amount(p.get(k)), 'currency': 'BDT', 'source_field': k} for k in ('base_price', 'min_price', 'suggested_price', 'max_price') if k in p},
                   'buying_basis': 'Source-labelled price types; account-specific buying eligibility not yet verified'},
        'stock': {'quantity': p.get('stock'), 'status': p.get('status')}, 'variants': variants,
        'extra': {k: v for k, v in p.items() if k not in ('description', 'gallery', 'variants')},
        'raw_data': {'product': p, 'content': data.get('content') or []}}


def classes(name):
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


def dropshipping(product, images_payload, body, url):
    doc = html.fromstring(body, base_url=url)
    ident = first(doc, '//*[@id="single_page_product_id"]')
    if ident is None or str(ident.get('value')) != str(product['id']):
        raise ValueError('Public product page does not match the authenticated reseller identity.')
    description = first(doc, '//*[@id="home"]')
    qty = first(doc, '//*[@id="product_stock"]')
    raw_quantity = qty.get('value') if qty is not None else None
    quantity = int(raw_quantity) if re.fullmatch(r'-?\d+', str(raw_quantity or '')) else None
    images = images_payload.get('images') or []
    own_images = []
    for entry in images:
        if str(entry.get('product_id')) != str(product['id']):
            raise ValueError('Gallery product identity mismatch; unrelated images refused.')
        base = entry.get('prefix_url') or 'https://dropshipping.com.bd/public/storage/'
        own_images.append(media(urljoin(base.rstrip('/')+'/', entry['image']),
            role='main' if not own_images else 'gallery', source_field='product-wise original image gallery'))
    shipping = [[text(cell) for cell in row.xpath('./th|./td')] for row in doc.xpath('//table[1]//tr')]
    options = [{'name': n.get('name') or n.get('id'), 'options':
        [{'value': o.get('value'), 'label': text(o)} for o in n.xpath('.//option')]} for n in doc.xpath('//select')]
    record = {'external_id': str(product['id']), 'sku': str(product.get('product_code') or ''),
        'url': url, 'title': product['name'], 'description': fragment(description) or product.get('details') or '',
        'media': own_images, 'variants': options,
        'prices': {**{k: {'amount': amount(product.get(k)), 'currency': 'BDT', 'source_field': k}
            for k in ('sale_price', 'reselling_price', 'reseller_price', 'reseller_sale_price') if k in product},
            'buying_basis': 'Authenticated reseller table: sale_price = Dropshipper Price; other prices are Customer / Retail Price'},
        'stock': {'quantity': quantity, 'status_code': product.get('status'),
                  'status': 'out_of_stock' if product.get('status') == 3 or (quantity is not None and quantity <= 0) else 'in_stock' if quantity is not None else 'unconfirmed',
                  'quantity_source': 'Original product_stock field; negative quantities remain preserved, never advertised as available'},
        'shipping': {'source_rate_table': shipping}, 'extra': {'account_authenticated': True},
        'raw_data': {'product': product, 'gallery': images, 'description_html': fragment(description),
                     'shipping_rows': shipping, 'raw_quantity': raw_quantity}}
    from .supplier_product_metadata import enrich_record
    return enrich_record(record,body,url)


def text(node):
    return ' '.join(node.text_content().split()) if node is not None else ''


def fragment(node):
    if node is None:
        return ''
    clean = deepcopy(node)
    for element in clean.xpath('.//script|.//style|.//form|.//input|.//button|.//iframe'):
        element.drop_tree()
    for element in clean.iter():
        for key in list(element.attrib):
            if key.lower().startswith('on') or re.search(r'nonce|csrf|token', key, re.I):
                del element.attrib[key]
    return html.tostring(clean, encoding='unicode',with_tail=False)


def first(doc, xpath):
    found = doc.xpath(xpath)
    return found[0] if found else None


def html_product(site, url, body, *, external_id=None, title='', categories=None):
    doc = html.fromstring(body, base_url=url)
    # CSS and scripts contain labels, example prices and stock class names, not
    # current product data. Never let them participate in text matching.
    for hidden in doc.xpath('//script|//style'):
        hidden.drop_tree()
    if doc.xpath('//input[@type="password"]'):
        raise ValueError('Sign-in page is not product content.')
    heading = first(doc, '//h1')
    description = None
    overview = None
    gallery = []
    root = None
    prices, stock, extra = {}, {}, {}
    if site in ('shopbase', 'dropbazar'):
        root = first(doc, f'//*[{classes("product-details-page")}]') if site == 'shopbase' else first(doc, '//*[@id="descriptionCopy"]/ancestor::*[.//img][1]')
        description = first(doc, '//*[@id="descriptionCopy"]')
        primary = first(doc, f'//*[{classes("position-relative")} and {classes("text-center")}]//img')
        if primary is not None and primary.get('src'):
            gallery.append(media(urljoin(url, primary.get('src')), role='main', source_field='primary product image'))
        # Group pictures can depict other colours/SKUs. Preserve, but do not represent them as this variant's own photos.
        if root is not None:
            for image in root.xpath('.//img[@src]'):
                if primary is not None and image.get('src') == primary.get('src'):
                    continue
                gallery.append(media(urljoin(url, image.get('src')), role='related_group', source_field='source group pictures', association='unconfirmed'))
        scope = text(root) if root is not None else text(doc)
        match = re.search(r'প্রাইস\s*[:ঃ]?\s*[৳\s]*([০-৯\d,.]+)', scope)
        if match:
            prices['reseller_price'] = {'amount': amount(match.group(1)), 'currency': 'BDT', 'source_label': 'প্রাইস'}
        suggested = re.search(r'সর্বোচ্চ\s*([০-৯\d,.]+)\s*টাকা', scope)
        if suggested:
            prices['suggested_max'] = {'amount': amount(suggested.group(1)), 'currency': 'BDT'}
        label=re.search(r'স্টক\s*[:ঃ]\s*(আছে|নেই)',scope)
        stock = {'status': ('in_stock' if label.group(1)=='আছে' else 'out_of_stock') if label else 'unconfirmed',
                 'source_label':label.group(0) if label else ''}
        title = title or (text(description).split(' Main Material:')[0] if description is not None else '')
    elif site == 'dropify':
        root = first(doc, f'//*[{classes("pdp-gallery-card")} or {classes("pd-image-col")}]')
        if root is None:
            raise ValueError('Expected original product gallery is absent; homepage/login redirects are not accepted.')
        for image in root.xpath('.//img[@src]'):
            gallery.append(media(urljoin(url, image.get('src')), role='main' if not gallery else 'gallery', source_field='pdp-gallery-card'))
        # The source has both a modern pdp layout and a legacy signed-in product layout.
        description = first(doc, '//*[@id="description"]')
        if description is None:
            description = first(doc, f'//*[{classes("pdp-desc-content")} or {classes("pd-desc-content")} or {classes("pdp-description")} or {classes("pdp-description-content")} or {classes("product-description")}]')
        overview = first(doc, f'//*[{classes("pdp-short-desc")} or {classes("pdp-overview")} or {classes("pdp-short-description")}]')
        legacy_content = doc.xpath(f'//*[{classes("pd-desc-content")}]')
        if len(legacy_content) > 1:
            extra['features_html'] = fragment(legacy_content[1])
        info = first(doc, f'//*[{classes("pd-info-col")}]')
        scope = text(info if info is not None else doc)
        wholesale = re.search(r'হোলসেল প্রাইস\s*([\d,.]+)', scope)
        suggested = re.search(r'সাজেস্টেড বিক্রয়মূল্য\s*([\d,.]+)', scope)
        prices = {'wholesale': {'amount': amount(wholesale.group(1)), 'currency': 'BDT'}} if wholesale else {}
        if suggested:
            prices['suggested'] = {'amount': amount(suggested.group(1)), 'currency': 'BDT'}
        if info is not None:
            for field, key in [('wholesale', 'wholesale'), ('suggested', 'suggested')]:
                value = first(info, f'.//*[{classes("pd-price-item-value")} and {classes(field)}]')
                if value is not None:
                    prices[key] = {'amount': amount(text(value)), 'currency': 'BDT',
                                   'source_label': 'Wholesale Price' if key == 'wholesale' else 'Suggested Price'}
            minimum = first(info, f'.//*[{classes("pd-min-selling")}]//strong')
            if minimum is not None:
                prices['minimum_selling_price'] = {'amount': amount(text(minimum)), 'currency': 'BDT'}
        quantity = re.search(r'স্টক:\s*([\d,]+)\s*ইউনিট', scope)
        stock = {'quantity': int(quantity.group(1).replace(',', '')) if quantity else None,
                 'status': 'out_of_stock' if 'স্টকে নেই' in scope[:3500] else 'in_stock' if 'স্টকে আছে' in scope[:3500] else 'unconfirmed'}
        if info is not None:
            state = first(info, f'.//*[{classes("pd-price-item-value")} and ({classes("stock-in")} or {classes("stock-out")})]')
            if state is not None:
                stock['status'] = 'out_of_stock' if 'stock-out' in state.get('class', '').split() else 'in_stock'
                stock['source_label'] = text(state)
            # Preserve exact radio option attributes without inferring quantities
            # from a generic In Stock label or maximum order form value.
            extra['variant_inputs'] = [dict(n.attrib) for n in info.xpath('.//input[@type="radio"]')]
            extra['account_price_verified'] = 'wholesale' in prices
        prices['buying_basis'] = 'Wholesale buying price and minimum selling price are separate; unknown quantity is not fabricated.'
    elif site == 'resellkori':
        root = first(doc, f'//*[{classes("single-product-content")}]')
        if root is None or heading is None:
            raise ValueError('Original WooCommerce product content is absent.')
        own_gallery = first(root, f'.//*[{classes("woocommerce-product-gallery__wrapper")}]')
        if own_gallery is not None:
            for image in own_gallery.xpath('.//img'):
                url_value = image.get('data-large_image') or image.get('data-src') or image.get('src')
                if url_value:
                    gallery.append(media(urljoin(url, url_value), role='main' if not gallery else 'gallery', source_field='woocommerce-product-gallery', srcset=image.get('srcset')))
        description = first(root, './/*[@id="tab-description"]')
        overview = first(root, f'.//*[{classes("woocommerce-product-details__short-description")}]')
        summary = first(root, f'.//*[{classes("summary")}]')
        scope = text(summary if summary is not None else root)
        reseller_btn = first(root, f'.//*[{classes("reselling-price-btn")}]')
        if reseller_btn is not None:
            scope = text(reseller_btn) + ' ' + scope
        for label, key in [('Market Price', 'market'), ('Reseller Price', 'reseller'), ('Wholesale Price', 'wholesale')]:
            value = re.search(re.escape(label) + r'\s*:\s*([\d,.]+)', scope)
            if value:
                prices[key] = {'amount': amount(value.group(1)), 'currency': 'BDT', 'source_label': label}
        prices['buying_basis'] = 'Reseller and wholesale rates retained separately; MOQ/account eligibility must be confirmed'
        qty = re.search(r'স্টক:\s*([০-৯\d,]+)', scope)
        stock = {'quantity': int(str(qty.group(1)).translate(str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')).replace(',', '')) if qty else None}
        extra['product_classes'] = root.get('class')
    else:
        raise ValueError('No verified full-content HTML mapping for this supplier.')
    title = text(heading) or title
    if not title or description is None:
        raise ValueError('Product title or verified description container is missing; mapper review required.')
    tables = []
    if description is not None:
        tables = [[text(cell) for cell in row.xpath('./th|./td')] for row in description.xpath('.//tr')]
    options = []
    if root is not None:
        selects = (root.xpath('.//form[contains(concat(" ",normalize-space(@class)," ")," cart ")]//select')
                   if site == 'resellkori' else root.xpath('.//select'))
        for select in selects:
            if (select.get('name') or select.get('id') or '').casefold() in ('rating', 'quantity'):
                continue
            options.append({'name': select.get('name') or select.get('id'), 'options':
                [{'value': option.get('value'), 'label': text(option)} for option in select.xpath('.//option')]})
    record = {'external_id': str(external_id or url.rstrip('/').split('/')[-1]), 'url': url,
        'title': title, 'description': fragment(description), 'short_description': fragment(overview),
        'categories': categories or [], 'media': gallery, 'prices': prices, 'stock': stock,
        'specifications': {'source_tables': tables} if tables else {}, 'extra': extra, 'variants': options,
        'raw_data': {'description_html': fragment(description), 'short_description_html': fragment(overview),
                     'source_product_attributes': dict(root.attrib) if root is not None else {}, 'prices': prices,
                     'product_html': fragment(root)}}
    from .supplier_product_metadata import enrich_record
    return enrich_record(record,body,url)
