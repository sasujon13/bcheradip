"""Staff-only, bounded explicit repricing. Never changes accepted orders."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib,json
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import DeliverySettings,Product,ProductVariant
from .permissions import IsCommerceAdmin
from .views import CommerceAdminAuthMixin
from .pricing import calculate_price,retail_prices,normalize_pricing_rules

def policy_signature(config):
    value=[normalize_pricing_rules(config.pricing_rules),config.cost_defaults,config.delivery_subsidy_enabled]
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()

class RepriceSupplierListingsView(CommerceAdminAuthMixin,APIView):
    permission_classes=[IsCommerceAdmin]
    permission_model=DeliverySettings
    permission_requirements={'POST':((DeliverySettings,'change'),(Product,'change'),(ProductVariant,'change'))}

    @transaction.atomic(using='ecommerce')
    def post(self,request):
        apply=serializers.BooleanField().run_validation(request.data.get('apply',False))
        cursor=serializers.IntegerField(min_value=0).run_validation(request.data.get('cursor',0))
        DeliverySettings.objects.using('ecommerce').get_or_create(pk=1)
        config=DeliverySettings.objects.using('ecommerce').select_for_update().get(pk=1);signature=policy_signature(config)
        if (apply or request.data.get('policy_signature')) and request.data.get('policy_signature')!=signature:
            return Response({'detail':'Pricing settings changed or were not previewed. Preview again before applying.'},status=409)
        scope=ProductVariant.objects.using('ecommerce').filter(is_active=True,
            product__attributes__manual_supplier_catalogue=True,product__supplier_offer__source_product__isnull=False).order_by('pk')
        upper=serializers.IntegerField(min_value=0).run_validation(request.data.get('upper_bound',0))
        if not upper:upper=scope.order_by('-pk').values_list('pk',flat=True).first() or 0
        scope=scope.filter(pk__lte=upper);total=scope.count()
        query=scope.filter(pk__gt=cursor)
        rows=list(query.values_list('pk','product_id')[:25]);counts=Counter();samples=[]
        from .supplier_service import costs_for,audit
        for pk,product_id in rows:
            with transaction.atomic(using='ecommerce'):
                # Same parent/variant lock ordering as checkout/publication.
                parent=Product.objects.using('ecommerce').select_for_update().get(pk=product_id)
                variant=ProductVariant.objects.using('ecommerce').select_for_update().get(pk=pk)
                rule=(parent.attributes or {}).get('_retail_pricing',{}).get(str(pk),{})
                try:
                    matches = (isinstance(rule,dict) and bool(rule) and
                        variant.price==Decimal(rule.get('applied_price','-1')) and
                        (rule.get('mode')!='sale' or variant.compare_at_price==Decimal(rule.get('regular_price','-1'))))
                except (InvalidOperation,TypeError,ValueError):
                    matches=False
                if not matches:
                    counts['manual_prices_preserved']+=1;continue
                offer=parent.supplier_offer
                if not offer.source_price or offer.source_price<=0 or variant.cost_price!=offer.source_price:
                    counts['needs_source_review']+=1;continue
                costs=costs_for(offer)
                suggestion=calculate_price(offer.source_price,{k:str(costs[k]) for k in
                    ('ads_cost','packaging_cost','returns_allowance','other_costs')},subsidy_enabled=False,rules=config.pricing_rules)
                source=offer.source_product
                minimum=Decimal(source.prices.get('minimum_selling_price',{}).get('amount') or '0') if source.supplier_id==7 else Decimal('0')
                pair=retail_prices(max(Decimal(suggestion['suggested_price']),minimum),config.pricing_rules)
                sale,regular=Decimal(pair['sale_price']),Decimal(pair['regular_price'])
                if variant.price==sale and variant.compare_at_price==regular:counts['unchanged']+=1;continue
                counts['changed']+=1
                if len(samples)<5:samples.append({'id':pk,'name':parent.name,'old_price':str(variant.price),'sale_price':str(sale),'regular_price':str(regular)})
                if apply:
                    old_price=str(variant.price)
                    variant.price=sale;variant.compare_at_price=regular
                    variant.save(using='ecommerce',update_fields=['price','compare_at_price','updated_at'])
                    pair.update(mode='sale',applied_price=str(sale),updated_at=timezone.now().isoformat(),policy_signature=signature)
                    parent.attributes={**parent.attributes,'_retail_pricing':{**parent.attributes.get('_retail_pricing',{}),str(pk):pair}}
                    parent.save(using='ecommerce',update_fields=['attributes','updated_at'])
                    audit('central_supplier_price_applied',request.user.pk,offer.supplier,offer,variant_id=pk,
                          old_price=old_price,new_price=str(sale),policy_signature=signature,accepted_orders_unchanged=True)
        next_cursor=rows[-1][0] if rows else cursor
        return Response({'processed':len(rows),'cursor':next_cursor,'upper_bound':upper,'total':total,'has_more':query.filter(pk__gt=next_cursor).exists(),
            'counts':dict(counts),'samples':samples,'policy_signature':signature,'applied':apply,'accepted_orders_unchanged':True})
