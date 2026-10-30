"""Owner-approved buying-price labels and persistent live verification reports."""
import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from lxml import html

from .supplier_source_parsers import amount, classes, first, text

SAMPLES = (
    {
        'site': 'resellkori', 'supplier_id': 8,
        'url': 'https://resellkori.com/product/silver-crest-grinder-machine-10000-wt/',
        'expected': '692.00', 'label': 'Reseller Price', 'price_property': 'prices.reseller',
        'html': '<a href="#" class="reselling-price-btn rk-popup-trigger" data-msg="এই প্রাইস টি আপনার জন্য, এই প্রাইসের উপর জত বেশি টাকা সেল দিবেন তত টাকাই আপনার প্রফিট। (মার্কেট প্রাইস এ ধারনা দেয়া আছে কত দাম চলতেছে এই প্রডাক্ট এর)">Reseller Price: 692৳</a>',
    },
    {
        'site': 'shopbase', 'supplier_id': 1,
        'url': 'https://shopbasebd.com/store/products/details/25307',
        'expected': '430.00', 'label': 'প্রাইস', 'price_property': 'prices.reseller_price',
        'html': '''<td width="32%">
											<button class="btn btn-sm btn-light w-100 pt-1 text-center pl-1 pr-1">
												প্রাইসঃ 
																									<span class="text-danger">৳৪৩০</span>
																							</button>
										</td>''',
    },
    {
        'site': 'business_koro', 'supplier_id': 2,
        'url': 'https://www.businesskoro.com/dashboard/products/black-paisley-hoodie-dropsoulder-combo',
        'expected': '860.00', 'label': 'আপনার পাইকারি মূল্য', 'price_property': 'prices.baseCost',
        'html': '<span class="rounded-xl bg-indigo-50 px-3 py-2 text-xs dark:bg-indigo-900/20"><span class="block text-indigo-500 dark:text-indigo-400">আপনার পাইকারি মূল্য</span><b class="text-base text-indigo-700 dark:text-indigo-300">৳860</b></span>',
    },
    {
        'site': 'dropbazar', 'supplier_id': 6,
        'url': 'https://dropbazarbd.com/admin/store/products/3559',
        'expected': '430.00', 'label': 'প্রাইস', 'price_property': 'prices.reseller_price',
        'html': '''<td width="32%">
                                    <button class="btn btn-sm btn-light w-100 pt-1 text-center pl-1 pr-1">
                                                                                    প্রাইস: <span class="text-danger">৳430</span>
                                                                            </button>
                                </td>''',
    },
    {
        'site': 'dropify', 'supplier_id': 7,
        'url': 'https://dropifybd.com/product/luxury-5-part-printed-nightwear-black',
        'expected': '1150.00', 'label': 'Wholesale Price', 'price_property': 'prices.wholesale',
        'html': '''<div class="pd-price-item">
                            <div class="pd-price-item-label">Wholesale Price</div>
                            <div class="pd-price-item-value wholesale">৳1,150</div>
                        </div>''',
    },
    {
        'site': 'uddoog', 'supplier_id': 3,
        'url': 'https://dropshop.com.bd/products/hoco-esd22-cool-anc-bluetooth-headphone',
        'expected': '1750.00', 'label': 'Base', 'price_property': 'prices.base_price',
        'html': '<div class="flex items-center justify-between gap-2"><dt class="text-slate-500">Base</dt><dd class="font-bold text-brand-deep">৳1,750</dd></div>',
    },
    {
        'site': 'selfshop', 'supplier_id': 4,
        'url': 'https://selfshop.com.bd/product/japani-silk-sharee-with-blouse-piece-3',
        'expected': '715.00', 'label': 'Price', 'price_property': 'prices.storefront_price',
        'html': '<div class="jsx-8b277976fcf884b text-gray-700 flex items-center text-sm gap-1"><div class="jsx-8b277976fcf884b flex items-center"><svg stroke="currentColor" fill="none" stroke-width="2" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" height="14" width="14" xmlns="http://www.w3.org/2000/svg"><path d="M16.5 15.5m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"></path><path d="M7 7a2 2 0 1 1 4 0v9a3 3 0 0 0 6 0v-.5"></path><path d="M8 11h6"></path></svg>715.00</div></div>',
    },
    {
        'site': 'dropshipping', 'supplier_id': 9,
        'url': 'https://www.dropshipping.com.bd/product/premium-stainless-steel-bar-pendant-chain-13321',
        'expected': '150.00', 'label': 'ড্রপশিপার প্রাইজ', 'price_property': 'prices.sale_price',
        'html': '''<span class="single_product_new_price" id="variant_wise_price">ড্রপশিপার প্রাইজঃ
                                            150
                                         TK</span>''',
    },
)


def parse_tree(markup):
    raw = markup if isinstance(markup, str) else markup.decode('utf-8', 'replace')
    wrapped = raw if '<html' in raw[:200].lower() else f'<div id="price-ensure-root">{raw}</div>'
    return html.fromstring(wrapped)


def extract_buying_price(site, markup):
    """Read the labelled buying price only. Retail/suggested/market stay unused."""
    doc = parse_tree(markup)
    if site == 'resellkori':
        node = first(doc, f'.//*[{classes("reselling-price-btn")}]')
        if node is None:
            node = first(doc, f'.//*[{classes("summary")}]')
        match = re.search(r'Reseller Price\s*:\s*([\d,.]+)', text(node) if node is not None else '')
        value = amount(match.group(1) if match else None)
        if value:
            return value, 'Reseller Price'
    if site in ('shopbase', 'dropbazar'):
        for button in doc.xpath('.//button'):
            if 'প্রাইস' in text(button):
                danger = first(button, f'.//*[{classes("text-danger")}]')
                value = amount(text(danger) if danger is not None else text(button))
                if value:
                    return value, 'প্রাইস'
    if site == 'business_koro':
        for node in doc.xpath('.//span'):
            if text(node).startswith('আপনার পাইকারি মূল্য'):
                bold = first(node, './/b')
                value = amount(text(bold) if bold is not None else text(node))
                if value:
                    return value, 'আপনার পাইকারি মূল্য'
    if site == 'dropify':
        node = first(doc, f'.//*[{classes("pd-price-item-value")} and {classes("wholesale")}]')
        value = amount(text(node)) if node is not None else None
        if value:
            return value, 'Wholesale Price'
    if site == 'uddoog':
        for dt in doc.xpath('.//dt'):
            if text(dt) == 'Base':
                dd = dt.getnext()
                value = amount(text(dd)) if dd is not None else None
                if value:
                    return value, 'Base'
    if site == 'selfshop':
        for label in doc.xpath('.//span|.//dt|.//label'):
            if re.fullmatch(r'Price\s*:', text(label), re.I):
                node = label.getparent()
                # SelfShop may show a struck-through reference price before
                # the actual payable Price. Read only text outside a
                # ``line-through`` subtree so the old reference amount can
                # never become Cheradip's buying cost.
                current_text = ' '.join(str(part).strip() for part in node.xpath(
                    './/text()[not(ancestor::*[contains(concat(" ", normalize-space(@class), " "), " line-through ")])]'
                ) if str(part).strip())
                value = amount(current_text)
                if value and Decimal(value) > 0:
                    return value, 'Price'
        # Historical owner-provided isolated price fragment only. Never search
        # every grey element of a full page (quantities/recommendations live there).
        for node in ([] if doc.xpath('.//h1') else doc.xpath(f'.//*[{classes("text-gray-700")}]')):
            value = amount(text(node))
            if value:
                return value, 'Price'
    if site == 'dropshipping':
        node = first(doc, './/*[@id="variant_wise_price" and contains(.,"ড্রপশিপার প্রাইজ")]')
        if node is None:
            node = first(doc, f'.//*[{classes("single_product_new_price")} and contains(.,"ড্রপশিপার প্রাইজ")]')
        value = amount(text(node)) if node is not None else None
        if value:
            return value, 'ড্রপশিপার প্রাইজ'
    return None, ''


def check_gold_html():
    rows = []
    for sample in SAMPLES:
        extracted, label = extract_buying_price(sample['site'], sample['html'])
        rows.append({
            'site': sample['site'], 'url': sample['url'], 'label': sample['label'],
            'price_property': sample['price_property'], 'expected': sample['expected'],
            'extracted': extracted, 'ok': extracted == sample['expected'] and label == sample['label'],
        })
    return rows


def collected_amount(url, price_property):
    from .models import SupplierSourceProduct
    key = price_property.split('.')[-1]
    path = urlsplit(url).path.rstrip('/')
    source = SupplierSourceProduct.objects.using('ecommerce').filter(url=url).first()
    if source is None and path:
        source = SupplierSourceProduct.objects.using('ecommerce').filter(url__endswith=path).first()
    if source is None:
        return None
    blob = source.prices or {}
    if key in blob and isinstance(blob[key], dict):
        return blob[key].get('amount')
    nested = blob.get('browser_buying_price') or {}
    if key in ('baseCost', 'browser_buying_price'):
        return (blob.get('baseCost') or nested or {}).get('amount')
    return None


def ensure_prices(*, live=True):
    """Always visit current pages; old owner amounts are never pass/fail targets."""
    from .supplier_price_probe import run_probe
    payload = {'status':'running','rows':[],'processed':0,'total':len(SAMPLES),
        'note':'Current browser buying prices compared with stored source records. No supplier orders.',
        'started_at':timezone_now(),'saved_at':timezone_now()}
    save_price_report(payload)
    for sample in SAMPLES:
        payload['activity']='Checking '+sample['site']
        save_price_report(payload)
        try:
            rows=run_probe(sample['site'],[sample])
            payload['rows'].extend(rows)
        except Exception as exc:
            from .supplier_browser import CollectionStopped
            payload['rows'].append({k:sample[k] for k in ('site','url','label','price_property')})
            payload['rows'][-1].update(live=None,collected=collected_amount(sample['url'],sample['price_property']),
                ok=False,extraction_ok=False,error=str(exc)[:240] if isinstance(exc,(ValueError,CollectionStopped)) else
                type(exc).__name__+': supplier sign-in/browser access needs review.')
        payload.update(processed=len(payload['rows']),saved_at=timezone_now())
        save_price_report(payload)
    payload.update(status='completed' if all(r['ok'] for r in payload['rows']) else 'completed_with_errors',
                   activity='Eight supplier price checks finished',saved_at=timezone_now())
    save_price_report(payload)
    return payload


def queue_price_check():
    import os
    import subprocess
    import sys
    from django.conf import settings
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime
    old=last_price_report() or {}
    stamp=parse_datetime(old.get('saved_at') or '')
    if old.get('status') in ('queued','running') and stamp and (timezone.now()-stamp).total_seconds()<1800:
        return old
    lock=price_report_path().with_suffix('.lock')
    if lock.exists() and (not stamp or (timezone.now()-stamp).total_seconds()>=1800 or old.get('status') not in ('queued','running')):
        lock.unlink(missing_ok=True)
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        return old or {'status':'running','rows':[],'activity':'Price verification is already running'}
    os.close(fd)
    result={'status':'queued','rows':[],'processed':0,'total':8,'saved_at':timezone_now(),
            'activity':'Starting browser verification'}
    save_price_report(result)
    try:
        with open(price_report_path().with_suffix('.log'),'a',encoding='utf-8') as output:
            subprocess.Popen([sys.executable,str(Path(settings.BASE_DIR)/'manage.py'),'ensure_supplier_prices','--live'],
                cwd=settings.BASE_DIR,stdout=output,stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except Exception:
        lock.unlink(missing_ok=True)
        result.update(status='failed',activity='Could not start browser verification')
        save_price_report(result)
    return result


def timezone_now():
    from django.utils import timezone
    return timezone.now().isoformat()


def price_report_path():
    from django.conf import settings
    folder = Path(settings.BASE_DIR) / 'private_suppliers' / 'catalog_sync'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder / 'ensure-prices-last.json'


def save_price_report(payload):
    import os
    import uuid
    path = price_report_path()
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp,path)


def last_price_report():
    path = price_report_path()
    if not path.exists():
        return None
    try:
        payload=json.loads(path.read_text(encoding='utf-8'))
        if payload.get('status') in ('queued','running'):
            from django.utils import timezone
            from django.utils.dateparse import parse_datetime
            stamp=parse_datetime(payload.get('saved_at') or '')
            if stamp and (timezone.now()-stamp).total_seconds()>300:
                payload.update(status='failed',activity='Price worker stopped reporting progress; retry to run a fresh check.')
        return payload
    except (OSError, ValueError):
        return None


def money(value):
    return Decimal(value) if value else None
