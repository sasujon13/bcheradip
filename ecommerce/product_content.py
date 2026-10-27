"""Conservative public presentation of original supplier properties and descriptions."""
import re
import unicodedata
from html import escape, unescape
from urllib.parse import urljoin, urlsplit
from lxml import html, etree
from .catalog_structure import clean, PROPERTY_TEMPLATES

ALIASES = {
    'material': 'Material', 'main material': 'Material', 'fabric': 'Material', 'fabrics': 'Material',
    'ম্যাটেরিয়াল': 'Material', 'ম্যাটেরিয়াল': 'Material', 'মেটেরিয়াল': 'Material', 'কাপড়': 'Material',
    'size': 'Size', 'sizes': 'Size', 'available sizes': 'Size', 'সাইজ': 'Size',
    't-shirt size': 'Size', 't shirt size': 'Size', 'size details': 'Size', 'available size': 'Size', 'body size': 'Size',
    'ফেব্রিক': 'Material', 'ফেব্রিক্স': 'Material', 'জিএসএম': 'Fabric weight',
    'fabrics type': 'Fabric type', 'fabric type': 'Fabric type', 'fit type': 'Fit',
    'color': 'Color', 'colour': 'Color', 'colors': 'Color', 'রং': 'Color', 'কালার': 'Color',
    'রঙ': 'Color', 'available colors': 'Color', 'available colours': 'Color',
    'দুইটি আকর্ষণীয় কালার': 'Color', 'দুইটি আকর্ষণীয় কালার': 'Color',
    'brand': 'Brand', 'ব্র্যান্ড': 'Brand', 'model': 'Model', 'model number': 'Model', 'মডেল': 'Model',
    'weight': 'Weight', 'ওজন': 'Weight', 'dimensions': 'Dimensions', 'dimension': 'Dimensions',
    'capacity': 'Capacity', 'storage': 'Capacity', 'volume': 'Volume', 'power': 'Power',
    'voltage': 'Voltage', 'battery': 'Battery', 'battery capacity': 'Battery', 'connectivity': 'Connectivity',
    'compatible with': 'Compatibility', 'compatibility': 'Compatibility', 'warranty': 'Warranty',
    'sleeve': 'Sleeve', 'sleeve type': 'Sleeve', 'fit': 'Fit', 'pattern': 'Pattern',
    'fabrication': 'Fabric weight', 'gsm': 'Fabric weight', 'pockets': 'Pockets',
    'care instructions': 'Care instructions', 'washing instructions': 'Care instructions',
    'package contents': 'Package contents', 'package includes': 'Package contents', 'in the box': 'Package contents',
    'number of pieces': 'Number of pieces', 'pieces': 'Number of pieces', 'closure': 'Closure',
    'ingredients': 'Ingredients', 'উপাদান': 'Ingredients', 'skin type': 'Skin type', 'hair type': 'Hair type',
    'directions': 'Directions', 'usage': 'Directions', 'expiry date': 'Expiry date', 'storage instructions': 'Storage',
    'age range': 'Age range', 'recommended age': 'Age range', 'gender': 'Gender',
    'movement': 'Movement', 'water resistance': 'Water resistance', 'waterproof': 'Water resistance',
    'author': 'Author', 'publisher': 'Publisher', 'isbn': 'ISBN', 'language': 'Language',
    'edition': 'Edition', 'pages': 'Pages', 'page count': 'Pages', 'length': 'Length', 'width': 'Width',
    'height': 'Height', 'depth': 'Depth', 'features': 'Features', 'feature': 'Features', 'type': 'Type',
    'product type': 'Type', 'condition': 'Condition', 'resolution': 'Resolution', 'processor': 'Processor',
    'ram': 'RAM', 'rom': 'ROM', 'frequency': 'Frequency', 'duration': 'Duration', 'license': 'License',
}
PRIVATE = re.compile(r'(^_|supplier|vendor|warehouse|source|wholesale|cost|price|profit|token|password|secret|credential|api.?key|access.?key|client.?id|headers?|cookies?|session|stock|quantity|sku|shipping|delivery|tax|\bauth(?:entication|orization)?\b|review|metadata|raw|url|image|html|script)', re.I)
MISSING = {'', '-', '—', 'n/a', 'na', 'none', 'null', 'undefined', 'unknown', 'not available', 'not specified'}


def document(value):
    try:
        return html.fragment_fromstring(str(value or ''), create_parent='div')
    except (ValueError, TypeError, etree.ParserError):
        return html.fragment_fromstring('<p>' + escape(str(value or '')) + '</p>', create_parent='div')


def plain(value):
    doc = document(value)
    for n in doc.xpath('.//script|.//style|.//iframe|.//form'): n.drop_tree()
    return clean(doc.text_content())


def content_lines(value):
    """Keep supplier line boundaries when interpreting labelled values/charts."""
    doc = document(value)
    for node in doc.xpath('.//script|.//style|.//iframe'): node.drop_tree()
    for node in doc.xpath('.//br|.//p|.//li|.//div|.//h2|.//h3|.//h4'):
        node.tail = '\n' + (node.tail or '')
    return unicodedata.normalize('NFKC', doc.text_content()).splitlines()


def safe_description(value, base_url=''):
    if not re.search(r'<[a-zA-Z][^>]*>', str(value or '')):
        value = '<p>' + escape(str(value or '')).replace('\n', '<br>') + '</p>'
    doc = document(value)
    for n in doc.xpath('.//script|.//style|.//iframe|.//form|.//input|.//button|.//object|.//embed|.//svg|.//link|.//meta'):
        n.drop_tree()
    allowed = {'p', 'br', 'ul', 'ol', 'li', 'strong', 'b', 'em', 'i', 'u', 'h2', 'h3', 'h4',
               'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote', 'img', 'div', 'span', 'pre'}
    for node in list(doc.iterdescendants()):
        if not isinstance(node.tag, str):
            if node.getparent() is not None: node.getparent().remove(node)
            continue
        if node.tag not in allowed:
            node.drop_tag()
            continue
        attrs = dict(node.attrib)
        node.attrib.clear()
        if node.tag in {'th', 'td'}:
            for key in ('colspan', 'rowspan'):
                if str(attrs.get(key, '')).isdigit() and 0 < int(attrs[key]) <= 20: node.set(key, attrs[key])
        if node.tag == 'img':
            src = urljoin(base_url, attrs.get('src', ''))
            if urlsplit(src).scheme not in ('http', 'https'):
                node.drop_tree()
                continue
            node.set('src', src); node.set('alt', attrs.get('alt', 'Product information'))
            node.set('loading', 'lazy')
    if not plain(etree.tostring(doc, encoding='unicode', method='html')) and not doc.xpath('.//img'):
        return ''
    if not list(doc): return '<p>' + escape(doc.text or '') + '</p>'
    return (escape(doc.text or '') + ''.join(etree.tostring(n, encoding='unicode', method='html') for n in doc))


def content_rows(source=None, attributes=None, variants=()):
    values, conflicts, evidence = {}, {}, {}
    def add(label, value, origin, structured=False):
        label = re.sub(r'^[^\w]+', '', unicodedata.normalize('NFKC', clean(label))).strip(' :：ঃ*-•')
        canonical = ALIASES.get(label.casefold())
        if not canonical and structured and 1 < len(label) < 65 and not PRIVATE.search(label): canonical = label
        if not canonical or PRIVATE.search(label): return
        if isinstance(value, dict):
            value = str(value.get('value') or value.get('name') or '') + (' ' + str(value.get('unitText')) if value.get('unitText') else '')
        if isinstance(value, (list, tuple)):
            value = ', '.join(dict.fromkeys(clean(v) for v in value if not isinstance(v, (dict, list))))
        if isinstance(value, bool): value = 'Yes' if value else 'No'
        if isinstance(value, (int, float)): value = str(value)
        text = plain(value)
        if text.casefold() in MISSING: return
        if canonical in {'Weight','Dimensions','Length','Width','Height','Depth','Volume','Capacity','Power','Voltage','Battery'}:
            units={'kg':'kg','g':'g','cm':'cm','mm':'mm','ml':'mL','l':'L','gb':'GB','mah':'mAh','w':'W','v':'V'}
            text=re.sub(r'(?<!\w)(\d+(?:\.\d+)?)\s*(kg|g|cm|mm|ml|l|gb|mah|w|v)\b',
                        lambda m:m[1]+' '+units[m[2].casefold()],text,flags=re.I)
        if canonical in values and values[canonical].casefold() != text.casefold():
            if canonical in ('Size', 'Color'):
                values[canonical] = ', '.join(dict.fromkeys([values[canonical], text]))
            elif text.casefold() not in values[canonical].casefold() and values[canonical].casefold() not in text.casefold():
                conflicts.setdefault(canonical, []).extend([values[canonical], text])
            return
        values[canonical] = text; evidence[canonical] = origin

    def structured(data, origin):
        if isinstance(data, dict):
            if data.get('name') and 'value' in data: add(data['name'], data['value'], origin, True)
            else:
                for k, v in data.items():
                    if k in ('structured_properties', 'additionalProperty'): structured(v, origin)
                    elif not PRIVATE.search(k): add(k, v, origin, True)
        elif isinstance(data, list):
            for row in data: structured(row, origin)

    def parse_html(value, origin):
        doc = document(value)
        for n in doc.xpath('.//script|.//style|.//iframe'): n.drop_tree()
        for row in doc.xpath('.//tr'):
            cells = row.xpath('./th|./td')
            if len(cells) == 2: add(cells[0].text_content(), cells[1].text_content(), origin, True)
        for node in doc.xpath('.//dt'):
            nxt = node.getnext()
            if nxt is not None and nxt.tag == 'dd': add(node.text_content(), nxt.text_content(), origin, True)
        for line in content_lines(value):
            match = re.match(r'^\s*([^:：ঃ]{2,60})\s*[:：ঃ]\s*(.+)$', line)
            if match: add(match[1], match[2], origin)
            else:
                match = re.match(r'^\s*(size|sizes|সাইজ)\s*[-–]\s*(.+)$', line, re.I)
                if match: add(match[1], match[2], origin)

    structured(attributes or {}, 'local attributes')
    if source:
        structured(source.specifications, 'supplier specifications')
        structured(source.extra.get('structured_attributes', {}), 'supplier structured data')
        for feature in source.features or []:
            if isinstance(feature, dict) and feature.get('html'): parse_html(feature['html'], 'supplier features')
            elif isinstance(feature, dict): structured(feature, 'supplier features')
            else: parse_html(feature, 'supplier features')
        parse_html(source.description, 'supplier description')
    for variant in variants:
        for n in (1, 2, 3):
            name, value = getattr(variant, f'option{n}_name', ''), getattr(variant, f'option{n}_value', '')
            if name and value: add(name, value, 'verified variant')
    root = ((attributes or {}).get('_catalog', {}).get('path') or [''])[0]
    preferred = PROPERTY_TEMPLATES.get(root, [])
    rows = [{'feature': k, 'value': v} for k, v in values.items() if k not in conflicts]
    rows.sort(key=lambda r: (preferred.index(r['feature']) if r['feature'] in preferred else 100, r['feature']))
    return rows, {k: list(dict.fromkeys(v)) for k, v in conflicts.items()}, evidence


def source_for(product):
    if not hasattr(product, '_content_source'):
        from .models import SupplierSourceProduct
        product._content_source = SupplierSourceProduct.objects.using('ecommerce').filter(linked_offers__imported_product_id=product.pk).defer('raw_data').first()
    return product._content_source


def variant_family(product):
    if hasattr(product, '_variant_family'): return product._variant_family
    from .models import ProductVariant
    source = source_for(product)
    qs = ProductVariant.objects.using('ecommerce').filter(is_active=True, product__status='active')
    if source:
        from .supplier_pilot import public_product_ids_for
        from .models import SupplierOffer
        family_ids = list(SupplierOffer.objects.using('ecommerce').filter(
            source_product_id=source.pk, imported_product_id__isnull=False,
        ).values_list('imported_product_id', flat=True))
        qs = qs.filter(product_id__in=[pk for pk in family_ids if public_product_ids_for(pk)])
    else: qs = qs.filter(product_id=product.pk)
    product._variant_family = list(qs.select_related('product').order_by('id'))
    return product._variant_family


def description_sizes(product, variants=None):
    """Explicit supplier size lists are order instructions, not invented supplier SKUs.

    Chart sizes are customer instructions against the original offer, not proof
    of size-specific inventory. Structured variants always take precedence.
    """
    variants = variant_family(product) if variants is None else variants
    if any(re.search(r'size|সাইজ', getattr(v, f'option{n}_name', ''), re.I)
           for v in variants for n in (1, 2, 3)):
        return []
    source = source_for(product)
    if not source:
        return []
    rows, conflicts, _ = content_rows(source)
    if 'Size' in conflicts:
        return []
    value = next((r['value'] for r in rows if r['feature'] == 'Size'), '')
    if not value:
        for line in content_lines(source.description or ''):
            labelled = re.match(r'^(?:body\s+)?size\s*=\s*(.+)$', line.strip(), re.I)
            if labelled:
                value = labelled[1]
                break
    # Stop before a chart or other labelled fields; only explicit size tokens.
    value = re.split(r'size\s*measurement|size\s*chart|chest\s*[:=]|length\s*[:=]', value, flags=re.I)[0]
    sizes = list(dict.fromkeys(m.upper() for m in re.findall(r'(?<!\w)(?:XXXXL|XXXL|XXL|XL|XXS|XS|S|M|L|[2-6]XL)(?!\w)', value, re.I)))
    numeric_translation = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
    if len(sizes) < 2:
        for line in content_lines(source.description or ''):
            normalized = line.strip().translate(numeric_translation)
            match = re.fullmatch(r'(?:সাইজ|(?:available\s+)?size)\s*[:ঃ：]?\s*(\d{2}(?:\s*[/,|]\s*\d{2})+)', normalized, re.I)
            if match:
                explicit = list(dict.fromkeys(re.findall(r'\d{2}', match[1])))
                if 2 <= len(explicit) <= 20:
                    return explicit
    if len(sizes) < 2:
        contents = [source.description or '', *[str(f.get('html') or f.get('value') or '') if isinstance(f, dict) else str(f) for f in source.features or []]]
        sizes = []
        size_token = r'(?:XXXXL|XXXL|XXL|XL|XXS|XS|S|M|L|[2-6]XL|\d{1,2}(?:-\d{1,2})?(?:Y|M)|\d{1,2}-\d{1,2})'
        chart_row = re.compile(
            r'^(' + size_token + r')\s*(?:Size\s*)?[=:•-]\s*\(?\s*(?:size\s+)?'
            r'(?:(?:sweet[ -]?shirt|hoodie|pant|body)\s+)?'
            r'(?:Chest|Length|Long|Waist|Body|বুক|লম্বা)\s*[:=>-]?\s*\d', re.I)
        for text in contents:
            has_size_heading = bool(re.search(r'size|সাইজ', plain(text), re.I))
            for line in content_lines(text):
                line = re.sub(r'^[^\w]+', '', line.strip()).replace('–', '-').replace('—', '-').replace('→', '=').replace('*', '')
                match = chart_row.match(line)
                if match and match[1].upper() not in sizes:
                    sizes.append(match[1].upper())
                elif has_size_heading:
                    simple = re.fullmatch(r'(XXXL|XXL|XL|XS|S|M|L)\s*=\s*\d{2}(?:\s*-\s*\d{2})?', line, re.I)
                    if simple and simple[1].upper() not in sizes:
                        sizes.append(simple[1].upper())
    return sizes if len(sizes) > 1 else []


def color_interpretation(product):
    """Conjunctions describe a mixed design until a staff member confirms choices."""
    decision = (getattr(product, 'attributes', {}) or {}).get('_catalog', {}).get('color_decision', {})
    source = source_for(product)
    rows, _, _ = content_rows(source) if source else ([], {}, None)
    original = next((r['value'] for r in rows if r['feature'] == 'Color'), '')
    ambiguous = bool(re.search(r'\s+(?:and|ও|এবং)\s+|\s*&\s*', original, re.I))
    translations = {'পিংক': 'Pink', 'গোলাপি': 'Pink', 'নীল': 'Blue', 'লাল': 'Red',
                    'সাদা': 'White', 'কালো': 'Black', 'সবুজ': 'Green', 'হলুদ': 'Yellow'}
    parts = re.split(r'\s+(?:and|ও|এবং)\s+|\s*&\s*', original, flags=re.I)
    display = ' & '.join(translations.get(clean(part), clean(part)) for part in parts) if ambiguous else original
    return {'mode': decision.get('mode', 'pending_mixed' if ambiguous else 'source'),
            'label': decision.get('label') or display, 'choices': decision.get('choices', []),
            'needs_review': ambiguous and not decision.get('mode'), 'original': original}


def description_colors(product, variants=None):
    """Only explicit supplier color lists become customer order instructions.

    These are not claimed to be separately reserved supplier SKUs. A source
    title naming one exact color takes precedence over a generic color chart.
    """
    variants = variant_family(product) if variants is None else variants
    if any(re.search(r'colou?r|রঙ', getattr(v, f'option{n}_name', ''), re.I)
           for v in variants for n in (1, 2, 3)):
        return []
    interpretation = color_interpretation(product)
    if interpretation['mode'] == 'separate':
        return interpretation['choices']
    if interpretation['mode'] in ('mixed', 'pending_mixed'):
        return []
    source = source_for(product)
    if not source:
        return []
    rows, conflicts, _ = content_rows(source)
    if 'Color' in conflicts:
        return []
    value = next((r['value'] for r in rows if r['feature'] == 'Color'), '')
    if not value or re.search(r'same as|as shown|random|assorted|multicolou?r|ছবির|যেকোন', value, re.I):
        return []
    colors = list(dict.fromkeys(clean(part) for part in re.split(r'\s*[,/|;]\s*|\s+(?:and|ও|এবং)\s+', value, flags=re.I)))
    if not 2 <= len(colors) <= 8 or any(not part or len(part) > 30 or any(
            unicodedata.category(char)[0] not in ('L', 'M') and char not in ' -' for char in part) for part in colors):
        return []
    title = clean(source.title or product.name)
    if any(re.search(r'[-–]\s*' + re.escape(color) + r'\s*$', title, re.I) for color in colors):
        return []
    return colors


def option_review(source, variants, allow_description_size=False, allow_description_color=False):
    """Descriptions can reveal missing choices but cannot create a sellable SKU."""
    rows, _, _ = content_rows(source)
    size = next((r['value'] for r in rows if r['feature'] == 'Size'), '')
    mentioned = set(re.findall(r'(?<!\w)(?:XXXL|XXL|XL|XS|S|M|L)(?!\w)', size, re.I))
    mapped = {str(getattr(v, f'option{n}_value', '')).casefold() for v in variants for n in (1,2,3)
              if re.search(r'size|সাইজ', getattr(v, f'option{n}_name', ''), re.I)}
    if len(mentioned) > 1 and not mapped and not allow_description_size: return True
    for label in ('Color','Capacity'):
        value=next((r['value'] for r in rows if r['feature']==label),'')
        if len([v for v in re.split(r'[,/|]',value) if v.strip()]) > 1:
            if label == 'Color' and allow_description_color: continue
            if not any(label.casefold() in getattr(v,f'option{n}_name','').casefold() for v in variants for n in (1,2,3)):
                return True
    if source.variants and not any(getattr(v,f'option{n}_value','') for v in variants for n in (1,2,3)):
        return True
    return False


def presentation(product):
    if hasattr(product, '_content_presentation'): return product._content_presentation
    source = source_for(product)
    variants = variant_family(product)
    from types import SimpleNamespace
    local_source = SimpleNamespace(specifications={}, extra={}, features=[], description=product.description)
    rows, conflicts, _ = content_rows(source or local_source, product.attributes, variants)
    original = product.description or product.short_description
    # Preserve local editorial changes; use original HTML when the stored shop
    # description is only the plain-text copy of that same supplier description.
    if source and (not plain(original) or plain(original) == plain(source.description)):
        original = source.description or source.short_description
    features = []
    if source:
        for feature in source.features or []:
            text = feature.get('html') or feature.get('value') or '' if isinstance(feature, dict) else feature
            if plain(text) and plain(text) != plain(original): features.append(safe_description(text, source.url))
    sizes = description_sizes(product, variants)
    colors = description_colors(product, variants)
    color_policy = color_interpretation(product)
    if color_policy['mode'] in ('mixed', 'pending_mixed'):
        for row in rows:
            if row['feature'] == 'Color': row['value'] = color_policy['label']
    for label, choices in (('Size', sizes), ('Color', colors)):
        if choices and not any(row['feature'] == label for row in rows):
            rows.append({'feature': label, 'value': ', '.join(choices)})
    review = bool((product.attributes or {}).get('_catalog', {}).get('variant_review'))
    if source and (not review or sizes or colors): review = option_review(source, variants, allow_description_size=bool(sizes), allow_description_color=bool(colors))
    result = {'specifications': rows, 'description_html': safe_description(original, source.url if source else ''),
              'features_html': features, 'purchasable': not review,
              'option_notice': 'Size or option choices are awaiting supplier verification.' if review else '',
              'conflicts': conflicts, 'description_sizes': sizes, 'description_colors': colors}
    product._content_presentation = result
    return result


def validate_variant_options(variant, requested_size='', requested_color=''):
    marker = (variant.product.attributes or {}).get('_catalog', {})
    review = marker.get('variant_review')
    # A later source refresh can introduce choices after a previous catalog
    # check. Recheck false/absent flags; a saved review hold needs staff clearance.
    sizes = description_sizes(variant.product)
    colors = description_colors(variant.product)
    if sizes and requested_size not in sizes:
        raise ValueError('Choose an available size before adding this product to Cart.')
    if requested_size and not sizes:
        raise ValueError('This size is no longer available. Please review the product options.')
    if colors and requested_color not in colors:
        raise ValueError('Choose an available color before adding this product to Cart.')
    if requested_color and not colors:
        raise ValueError('This color is no longer available. Please review the product options.')
    if not review or sizes or colors:
        source = source_for(variant.product)
        review = bool(source and option_review(source, variant_family(variant.product), allow_description_size=bool(sizes), allow_description_color=bool(colors)))
    if review:
        raise ValueError('This product’s size or option choices need supplier verification before ordering.')
