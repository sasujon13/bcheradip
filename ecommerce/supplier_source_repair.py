"""Restore only labelled source observations; never manufacture missing facts."""
from django.db import transaction
from .models import SupplierSourceProduct, SupplierOffer


@transaction.atomic(using='ecommerce')
def restore_observations(source_id):
    from .supplier_source_publish import source_variants, stock_observed_at
    source = SupplierSourceProduct.objects.using('ecommerce').get(pk=source_id)
    if source.extra.get('browser_preferred') and (source.extra.get('browser_verification') or {}).get('state') not in ('verified','unavailable'):
        return 0
    observed = stock_observed_at(source)
    try:
        variants = source_variants(source)
    except ValueError:
        variants = []
    negative = str(source.stock.get('status') or '').lower() in ('out_of_stock','missing')
    changed = 0
    for offer in SupplierOffer.objects.using('ecommerce').select_for_update().filter(source_product=source).exclude(state='excluded'):
        if offer.observed_at and observed and offer.observed_at > observed:
            continue
        matching = [v for v in variants if offer.variant_id in (v['id'],v['legacy_id']) or
            (offer.variant_id.startswith('catalogue-type-') and not source.variants and not v['spec'])]
        if len(matching) == 1:
            row = matching[0]
            values = {'source_price':row['cost'],'quantity':row['quantity'],
                'availability':'in_stock' if row['quantity'] or row.get('confirmation_required') else 'out_of_stock',
                'currency':'BDT','single_unit':True,'observed_at':observed}
        elif (source.supplier_id == 4 and source.extra.get('account_authenticated') and
              source.prices.get('pricing_locked') is False and str(source.stock.get('status')).lower() == 'active'):
            # Account storefront price includes SelfShop's own commission;
            # the lower internal wholesale figure is not the payable price.
            from decimal import Decimal
            amount = source.prices.get('storefront_price',{}).get('amount')
            cost = Decimal(str(amount or '0'))
            quantity = source.stock.get('qty')
            if not cost.is_finite() or cost <= 0 or isinstance(quantity,bool) or not isinstance(quantity,int):
                continue
            values = {'source_price':cost,'quantity':quantity,
                'availability':'in_stock' if quantity > 0 else 'out_of_stock',
                'currency':'BDT','observed_at':observed,
                'single_unit':source.stock.get('minimum_qty') in (None,1,'1')}
        elif negative:
            values = {'availability':str(source.stock['status']).lower(),'quantity':0,'observed_at':observed}
        else:
            continue
        fields = [key for key,value in values.items() if getattr(offer,key) != value]
        if not fields:
            continue
        for key,value in values.items(): setattr(offer,key,value)
        offer.save(using='ecommerce',update_fields=[*fields,'updated_at'])
        changed += 1
    return changed
