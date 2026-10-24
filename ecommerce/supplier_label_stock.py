"""Read-only, own-page buying price and labelled availability for three inspected suppliers."""
from decimal import Decimal
from urllib.parse import urlsplit
from lxml import html
from django.utils import timezone
from .supplier_source_parsers import html_product,first,text,classes

SITES = {1:'shopbase',6:'dropbazar',7:'dropify'}


def missing_stock(source):
    # A 404 is not a zero quantity or a newly verified buying price.
    return {'prices':source.prices,'stock':{'status':'unconfirmed'},'extra':source.extra}


def read_stock(client, source):
    from .supplier_source_publish import norm
    if source.supplier_id not in SITES or client.site != SITES[source.supplier_id]:
        raise ValueError('Unverified supplier mapping.')
    response=client.request(source.url)
    if urlsplit(response.url).path.rstrip('/') != urlsplit(source.url).path.rstrip('/'):
        raise ValueError('Source redirected away from this exact saved product.')
    doc=html.fromstring(response.content)
    if source.supplier_id in (1,6):
        ids=doc.xpath('//input[@name="product_id"]/@value')
        if ids != [source.external_id]:
            raise ValueError('Own product identifier changed; review required.')
    else:
        # Description content may contain its own H1 headings. Combining every
        # H1 falsely rejects the six verified source products which use them.
        heading=first(doc,f'//h1[{classes("pd-name")}]')
        if heading is None:heading=first(doc,'//h1')
        if norm(text(heading)) != norm(source.title):
            raise ValueError('Product title changed; exact mapping needs review.')
    data=html_product(client.site,response.url,response.content,external_id=source.external_id,title=source.title)
    if data.get('variants') or data.get('extra',{}).get('variant_inputs'):
        raise ValueError('Source now has unmapped options; no stock confirmation invented.')
    field='wholesale' if source.supplier_id==7 else 'reseller_price'
    cost=Decimal(data['prices'].get(field,{}).get('amount') or '0')
    if not cost.is_finite() or cost<=0:
        raise ValueError('Current account buying price is unavailable.')
    if source.supplier_id==7 and not data.get('extra',{}).get('account_price_verified'):
        raise ValueError('Signed-in wholesale price is not verified.')
    quantity=data['stock'].get('quantity')
    if quantity is not None and (isinstance(quantity,bool) or not isinstance(quantity,int) or quantity<0):
        raise ValueError('Invalid quantity; no stock count invented.')
    return data


def remember_stock(source, data):
    """Preserve original full-content time; advance only an actual price/stock check."""
    checked=timezone.now()
    extra={**source.extra,'price_stock_checked_at':checked.isoformat()}
    if source.supplier_id==7:
        extra['account_price_verified']=data.get('extra',{}).get('account_price_verified',False)
    type(source).objects.using('ecommerce').filter(pk=source.pk).update(
        prices=data['prices'],stock=data['stock'],extra=extra,updated_at=checked)
    source.prices,source.stock,source.extra=data['prices'],data['stock'],extra
    return checked


def refresh_existing_offers(source, data, checked):
    """A newly unavailable own page must immediately hold an older live listing."""
    from copy import deepcopy
    from .models import SupplierOffer
    from .supplier_service import snapshot_row
    status=data['stock'].get('status')
    field='wholesale' if source.supplier_id==7 else 'reseller_price'
    for offer in SupplierOffer.objects.using('ecommerce').filter(source_product=source,imported_product__isnull=False):
        snapshot_row(offer.supplier,{'external_id':offer.external_id,'variant_id':offer.variant_id,
            'vendor_id':offer.vendor_id,'warehouse_id':offer.warehouse_id,'title':offer.title,
            'url':offer.url,'identity':deepcopy(offer.identity),'source_price':data['prices'][field]['amount'],
            'quantity':data['stock'].get('quantity'),'currency':'BDT','single_unit':True,
            'availability':status if status in ('in_stock','out_of_stock') else 'unconfirmed',
            'observed_at':checked.isoformat()},update=True)
