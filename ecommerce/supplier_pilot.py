"""Expiring, individually verified manual fulfilment. Never submits supplier orders."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from .models import DeliverySettings, Product, SupplierOffer, SupplierPilotCheck
from .supplier_service import assert_current, audit, costs_for, MONEY_COSTS
from .supplier_delivery import validate_rates

CHECKS = ('price', 'variant', 'stock', 'delivery', 'margin', 'content')
MESSAGE = 'This supplier product needs a current staff pilot verification. Automatic supplier purchasing is OFF.'
_public_ids_cache = None


def _catalogue_cache():
    """Use a cache shared by Gunicorn workers for the short-lived public ID set."""
    global _public_ids_cache
    import sys
    if 'test' in sys.argv:
        from django.core.cache import cache
        return cache
    if _public_ids_cache is None:
        from django.core.cache.backends.filebased import FileBasedCache
        cache_dir = os.environ.get('ECOMMERCE_PUBLIC_CACHE_DIR') or os.path.join(
            tempfile.gettempdir(), 'cheradip-ecommerce-public-cache')
        _public_ids_cache = FileBasedCache(cache_dir, {'OPTIONS': {'MAX_ENTRIES': 32, 'CULL_FREQUENCY': 2}})
    return _public_ids_cache


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def facts(product, offer):
    """Stock is consumed by ordinary locked checkout; content/cost changes invalidate checks."""
    return dict(product={k:getattr(product,k) for k in ('id','name','description','short_description','category_id','brand_id','product_type','attributes','supplier_delivery_rates','delivery_dhaka_charge','delivery_outside_dhaka_charge','cod_percent')},
        variants=list(product.variants.order_by('pk').values('id','title','sku','price','cost_price','currency','weight_grams','is_active','requires_shipping','allow_backorder',
            'option1_name','option1_value','option2_name','option2_value','option3_name','option3_value')),
        images=list(product.images.order_by('pk').values('url','position','variant_id')),
        source={k:getattr(offer,k) for k in ('id','supplier_id','external_id','variant_id','vendor_id','warehouse_id','identity','source_price','currency','weight_grams','costs','excluded_reason')})


def verified_context(product):
    try:
        offer=SupplierOffer.objects.using('ecommerce').select_related('supplier','current_decision').get(imported_product=product)
    except SupplierOffer.DoesNotExist:
        raise ValueError('Choose an imported supplier product, not ordinary shop inventory.')
    decision=assert_current(offer)
    now=timezone.now()
    if not decision.approved_at or not offer.supplier.enabled or not offer.supplier.terms_confirmed or offer.excluded_reason:
        raise ValueError('A current approved screening decision and enabled supplier are required.')
    if not offer.observed_at or not now-timedelta(hours=24) <= offer.observed_at <= now:
        raise ValueError('Check source price and exact variant stock within the past 24 hours first.')
    variants=list(product.variants.filter(is_active=True))
    if len(variants)!=1:
        raise ValueError('Pilot releases support one verified source variant per product; do not silently combine variants.')
    variant=variants[0]
    if (not variant.requires_shipping or variant.allow_backorder or variant.currency!='BDT' or
            not variant.weight_grams or variant.weight_grams!=offer.weight_grams or
            variant.cost_price!=offer.source_price or variant.price<=0):
        raise ValueError('Verify BDT buying price, actual parcel weight, physical variant and no-backorder inventory.')
    if offer.availability!='in_stock' or not offer.single_unit or offer.quantity is None or variant.stock>offer.quantity:
        raise ValueError('Exact source variant quantity must be confirmed; parent stock or unknown stock is insufficient.')
    rates=validate_rates(product.supplier_delivery_rates)
    if not rates.get('dhaka') or not rates.get('outside'):
        raise ValueError('Record verified supplier area/weight tariffs for both delivery areas first.')
    if product.delivery_dhaka_charge is not None or product.delivery_outside_dhaka_charge is not None:
        raise ValueError('Pilot uses the verified supplier tariff directly, not an additional product delivery fee.')
    if not product.images.exists() or not product.description.strip():
        raise ValueError('Review real product imagery and description before pilot release.')
    costs=costs_for(offer)
    floor=offer.source_price+sum((costs[k] for k in MONEY_COSTS),Decimal('0'))+costs['fees']+costs['taxes']
    if variant.price<=floor:
        raise ValueError('Selling price must cover the verified source cost and all non-delivery allowances with positive profit.')
    return offer,variant,floor


def order_facts(order):
    return dict(id=order.pk,total=order.grand_total,subtotal=order.subtotal,discount=order.discount_total,
        delivery=order.shipping_total,cod=order.cod_total,address=order.shipping_address,
        items=list(order.items.order_by('pk').values('product_id','variant_id','quantity','unit_price')))


@transaction.atomic(using='ecommerce')
def record_check(check, actor, *, save=True):
    permission='confirm_supplier_pilot' if check.order_id else 'publish_supplier_pilot'
    if not actor.is_active or not actor.is_staff or not (actor.is_superuser or actor.has_perm('ecommerce.'+permission)):
        raise ValueError('The corresponding supplier pilot permission is required.')
    if not (actor.is_superuser or actor.has_perm('ecommerce.change_order' if check.order_id else 'ecommerce.change_product')):
        raise ValueError('Product publication or order management permission is also required.')
    if not isinstance(check.checks,dict) or set(check.checks)!=set(CHECKS) or any(check.checks[k] is not True for k in CHECKS):
        raise ValueError('Record every price, exact variant, stock, delivery, margin and content check explicitly.')
    if not check.note.strip(): raise ValueError('Record the source quote/reference and verification details.')
    now=timezone.now()
    if not check.expires_at or not now<check.expires_at<=now+timedelta(hours=24):
        raise ValueError('Pilot verification must expire within 24 hours; recheck rather than extending stale stock.')
    product=Product.objects.using('ecommerce').select_for_update().get(pk=check.product_id)
    offer,variant,floor=verified_context(product)
    from .pricing import money
    check.expected_source_price=money(check.expected_source_price,'Verified buying price')
    check.expected_selling_price=money(check.expected_selling_price,'Verified selling price')
    if check.expected_source_price!=offer.source_price or (not check.order_id and check.expected_selling_price!=variant.price):
        raise ValueError('Buying or selling price changed. Review the actual prices again.')
    if check.verified_quantity<1 or check.verified_quantity>offer.quantity:
        raise ValueError('Verified quantity must be positive and no greater than the exact source variant quantity.')
    if not check.order_id and variant.stock>check.verified_quantity:
        raise ValueError('Local saleable stock exceeds the staff-verified pilot quantity.')
    snapshot={'product':facts(product,offer),'decision':offer.current_decision_id}
    if check.order_id:
        from .models import Order
        order=Order.objects.using('ecommerce').select_for_update().get(pk=check.order_id)
        item=order.items.filter(product_id=product.pk,variant_id=variant.pk).first()
        if order.status!='pending' or not item or item.quantity>check.verified_quantity:
            raise ValueError('Check a pending order containing this exact variant and sufficient verified supplier quantity.')
        if check.expected_selling_price!=item.unit_price:
            raise ValueError('Use the accepted order item price, not a newly changed catalogue price.')
        _order_shipping(order)
        if order.payment_status in ('refunded',): raise ValueError('Refunded orders cannot be confirmed.')
        # Do not reprice accepted orders; allocate coupon proportionally for viability.
        discounted=item.unit_price*(1-order.discount_total/order.subtotal) if order.subtotal else Decimal('0')
        if discounted<=floor:
            raise ValueError('The accepted discounted item price no longer covers costs. Resolve manually; never silently reprice.')
        snapshot['order']=order_facts(order)
    check.snapshot=json.loads(json.dumps(snapshot,default=str)); check.fingerprint=digest(snapshot); check.actor_id=actor.pk
    if not save: return check
    check.save(using='ecommerce')
    audit('manual_pilot_order_check' if check.order_id else 'manual_pilot_release',actor.pk,offer.supplier,offer,
          check_id=check.pk,product_id=product.pk,order_id=check.order_id,expires_at=check.expires_at.isoformat(),automatic_purchasing=False)
    return check


def current_release(product):
    offer,variant,_=verified_context(product)
    for check in SupplierPilotCheck.objects.using('ecommerce').filter(product=product,order__isnull=True,revoked_at__isnull=True,expires_at__gt=timezone.now()).order_by('-pk'):
        snapshot={'product':facts(product,offer),'decision':offer.current_decision_id}
        if check.fingerprint==digest(snapshot) and variant.stock<=check.verified_quantity:
            return check
    raise ValueError(MESSAGE)


def public_product_ids(*,include_inactive=False,include_manual=True):
    return _public_product_ids(include_inactive=include_inactive, include_manual=include_manual)


def _public_product_ids(*,include_inactive=False,include_manual=True):
    """Return currently releasable catalogue IDs, amortizing storefront checks briefly.

    Checkout always runs the uncached release/stock checks. This short cache only
    avoids repeating expensive public-list eligibility fingerprints on every
    storefront reload; detail requests can use the single-product helper below.
    """
    # The list endpoint already caches public responses for fifteen seconds.
    # Share that same brief snapshot across batch/filter requests during bulk
    # updates instead of invalidating it on every single imported image/offer.
    # Details and checkout use uncached single-product eligibility checks.
    import sys
    cache=_catalogue_cache()
    burst_key=f'ecommerce:public-product-ids:burst:v7:{int(include_inactive)}:{int(include_manual)}'
    if 'test' not in sys.argv:
        cached=cache.get(burst_key)
        if cached is not None:return list(cached)
    # A compact database revision invalidates the shared short cache as soon as
    # a listing, offer, release, supplier, or catalogue mode changes.
    from .models import Supplier, SupplierPolicy
    product_state=Product.objects.using('ecommerce').aggregate(Max('updated_at'), active_count=Count('pk',filter=Q(status='active')))
    revision=(
        product_state['updated_at__max'], product_state['active_count'],
        SupplierOffer.objects.using('ecommerce').aggregate(Max('updated_at'))['updated_at__max'],
        SupplierPilotCheck.objects.using('ecommerce').aggregate(Max('updated_at'))['updated_at__max'],
        Supplier.objects.using('ecommerce').aggregate(Max('updated_at'))['updated_at__max'],
        SupplierPolicy.objects.using('ecommerce').filter(pk=1).values_list('catalogue_mode',flat=True).first(),
    )
    # Python's built-in hash is randomized per process. Use a deterministic key
    # so every worker shares the same FileBasedCache entry.
    revision_key=hashlib.sha256(json.dumps(revision, sort_keys=True, default=str).encode()).hexdigest()
    cache_key=f'ecommerce:public-product-ids:v6:{int(include_inactive)}:{int(include_manual)}:{revision_key}'
    cached=cache.get(cache_key)
    if cached is not None:
        if 'test' not in sys.argv:cache.set(burst_key,tuple(cached),15)
        return list(cached)
    ids=SupplierPilotCheck.objects.using('ecommerce').filter(order__isnull=True,revoked_at__isnull=True,expires_at__gt=timezone.now()).values_list('product_id',flat=True).distinct()
    valid=[]
    products=Product.objects.using('ecommerce').filter(pk__in=ids,variants__is_active=True,variants__stock__gt=0).distinct()
    if not include_inactive: products=products.filter(status='active')
    for product in products:
        try: current_release(product)
        except (ValueError,SupplierOffer.DoesNotExist): continue
        valid.append(product.pk)
    if include_manual:
        from .manual_catalogue import public_ids, price_preview_ids
        valid=list(set(valid) | set(public_ids()) | set(price_preview_ids()))
    cache.set(cache_key,tuple(valid),15)
    if 'test' not in sys.argv:cache.set(burst_key,tuple(valid),15)
    return valid


def public_product_ids_for(product_id):
    """Check only one supplier product when serving its details URL."""
    from .manual_catalogue import public_ids
    from .models import SupplierOffer
    if not SupplierOffer.objects.using('ecommerce').filter(imported_product_id=product_id).exists():
        return [product_id]
    try:
        product=Product.objects.using('ecommerce').get(pk=product_id,status='active')
    except Product.DoesNotExist:
        return []
    try:
        current_release(product)
        return [product_id]
    except (ValueError,SupplierOffer.DoesNotExist):
        from .manual_catalogue import price_preview_ids
        return [product_id] if (public_ids().filter(imported_product_id=product_id).exists() or price_preview_ids().filter(pk=product_id).exists()) else []


def validate_checkout(lines,totals,*,lock=False):
    """Coupon reductions must not turn a previously approved item into a loss."""
    lines=list(lines)
    if lock:
        # Checkout holds its transaction until inventory/order writes commit.
        # A concurrent source update cannot change buying costs mid-acceptance.
        list(SupplierOffer.objects.using('ecommerce').select_for_update().filter(
            imported_product_id__in=[v.product_id for v,q in lines]).order_by('pk'))
    pilot=False
    for variant,quantity in lines:
        if not SupplierOffer.objects.using('ecommerce').filter(imported_product_id=variant.product_id).exists(): continue
        from .manual_catalogue import is_manual, checkout_check
        if is_manual(variant.product):
            checkout_check(variant, quantity)
            continue
        pilot=True
        current_release(variant.product)
        _,_,floor=verified_context(variant.product)
        discounted=variant.price*(1-totals['discount_total']/totals['subtotal']) if totals['subtotal'] else Decimal('0')
        if discounted<=floor:
            raise ValueError('A supplier item would lose money after this discount. Ask staff to review; the accepted price was not changed.')
    if pilot:
        shipping=sum((Decimal(s['charged']) for s in totals['delivery_details'].get('supplier_shipments',[])),Decimal('0'))
        if totals['shipping_total']<shipping:
            raise ValueError('This delivery discount would subsidise supplier shipping. Pilot supplier tariffs must be recovered in full.')


def _order_shipping(order):
    import re
    from .models import ProductVariant
    from .supplier_delivery import split_supplier_delivery
    rows=list(order.items.all())
    variants={v.pk:v for v in ProductVariant.objects.using('ecommerce').filter(pk__in=[i.variant_id for i in rows]).select_related('product')}
    if len(variants)!=len({i.variant_id for i in rows}): raise ValueError('An order variant is missing. Resolve manually.')
    district=re.sub(r'[\s._-]+','',str(order.shipping_address.get('district','')).casefold())
    if not district or order.shipping_address.get('country_code','BD').upper()!='BD': raise ValueError('Verify the supported delivery destination.')
    policy=DeliverySettings.current()
    fallback=policy.dhaka_charge if district in {'dhaka','dhakadistrict','ঢাকা','ঢাকাজেলা'} else policy.outside_dhaka_charge
    _,shipments=split_supplier_delivery([(variants[i.variant_id],i.quantity) for i in rows],district in {'dhaka','dhakadistrict','ঢাকা','ঢাকাজেলা'},fallback)
    if order.shipping_total<sum((Decimal(s['charged']) for s in shipments),Decimal('0')):
        raise ValueError('Current supplier shipment costs exceed accepted delivery recovery. Resolve manually; do not reprice the accepted order.')


def require_order_checks(order):
    checked_shipping=False
    for product in Product.objects.using('ecommerce').filter(pk__in=order.items.values('product_id'),supplier_offer__isnull=False):
        from .manual_catalogue import is_manual
        if is_manual(product):
            # These orders are explicitly staff-fulfilled; source links are in
            # Manage. Do not retroactively apply research/pilot publication gates.
            continue
        if not checked_shipping: _order_shipping(order); checked_shipping=True
        offer,_,_=verified_context(product)
        expected=digest({'product':facts(product,offer),'decision':offer.current_decision_id,'order':order_facts(order)})
        if not SupplierPilotCheck.objects.using('ecommerce').filter(order=order,product=product,revoked_at__isnull=True,expires_at__gt=timezone.now(),fingerprint=expected).exists():
            raise ValueError('Record a fresh staff supplier fulfilment check for every supplier item before confirming or fulfilling this order.')
