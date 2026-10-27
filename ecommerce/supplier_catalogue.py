"""Audited catalogue controls independent of research for manual fulfilment."""
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Supplier, SupplierOffer, SupplierPolicy, Product
from .supplier_service import policy, audit
from .manual_catalogue import eligible_offers, purchasable_offers, queue_imports
from .permissions import IsCommerceAdmin
from .views import CommerceAdminAuthMixin


class CatalogueModeView(CommerceAdminAuthMixin,APIView):
    permission_classes=[IsCommerceAdmin]
    permission_model=Supplier
    permission_requirements={'POST':((Supplier,'view'),)}

    def post(self,request):
        from .supplier_api import require
        require(request.user,'manage_supplier_catalogue')
        mode=serializers.ChoiceField(choices=['all','filtered']).run_validation(request.data.get('mode'))
        preview=serializers.BooleanField().run_validation(request.data.get('preview',True))
        config=policy()
        offers=eligible_offers(mode)
        from .supplier_pilot import public_product_ids
        pilot_ids=public_product_ids(include_inactive=True,include_manual=False)
        valid=list(purchasable_offers(mode).values_list('imported_product_id',flat=True))+pilot_ids
        from .manual_catalogue import price_preview_ids
        if mode == 'all': valid += list(price_preview_ids(include_inactive=True))
        linked=Product.objects.using('ecommerce').filter(supplier_offer__isnull=False)
        restore=linked.filter(pk__in=valid).exclude(status='active')
        archive=linked.exclude(pk__in=valid).exclude(status='archived')
        summary=dict(mode=mode,eligible_products=offers.count(),new_products=offers.filter(imported_product=None).count(),restorable_products=restore.count(),archive_products=archive.count(),
            unverified_hidden=SupplierOffer.objects.using('ecommerce').exclude(pk__in=offers.values('pk')).count(),
            scope='All supplier-linked shop products. Ordinary inventory, customers, orders and saved research are unchanged.',
            detail='Both modes require original supplier photos, complete descriptions, current buying prices and confirmed available stock. Keep All waives market screening only. Keep Filtered additionally requires research approval. Incomplete and permanently excluded products remain hidden.')
        if preview:
            token=signing.dumps(dict(actor=request.user.pk,mode=mode,revision=config.catalogue_revision,rule='verified-catalogue-v3'),salt='supplier-catalogue-mode')
            return Response({**summary,'preview':True,'preview_token':token})
        try:
            signed=signing.loads(request.data.get('preview_token',''),salt='supplier-catalogue-mode',max_age=600)
        except (signing.BadSignature,TypeError):
            raise ValidationError('Preview this catalogue change again; the confirmation expired.')
        with transaction.atomic(using='ecommerce'):
            config=SupplierPolicy.objects.using('ecommerce').select_for_update().get(pk=1)
            if signed!=dict(actor=request.user.pk,mode=mode,revision=config.catalogue_revision,rule='verified-catalogue-v3'):
                raise ValidationError('Catalogue rules, mode or author changed. Preview again.')
            pilot_ids=public_product_ids(include_inactive=True,include_manual=False)
            valid=list(purchasable_offers(mode).values_list('imported_product_id',flat=True))+pilot_ids
            if mode == 'all': valid += list(price_preview_ids(include_inactive=True))
            # Usually zero rows: do not rewrite 25,000 JSON fields every time
            # the owner switches visibility. Only adopt older draft imports.
            for product in linked.filter(pk__in=valid).exclude(pk__in=pilot_ids).filter(~Q(attributes__has_key='manual_supplier_catalogue') | Q(attributes__manual_supplier_catalogue=False)).only('pk','attributes'):
                Product.objects.using('ecommerce').filter(pk=product.pk).update(attributes={**(product.attributes or {}),'manual_supplier_catalogue':True})
            restore=linked.filter(pk__in=valid).exclude(status='active')
            archive=linked.exclude(pk__in=valid).exclude(status='archived')
            if restore.exists() or archive.exists(): require(request.user,'change_product')
            if mode=='all': require(request.user,'change_product')
            archived=archive.update(status='archived',updated_at=timezone.now()); restored=restore.update(status='active',updated_at=timezone.now())
            config.catalogue_mode=mode; config.catalogue_revision+=1
            config.save(using='ecommerce',update_fields=['catalogue_mode','catalogue_revision','updated_at'])
            jobs=queue_imports(request.user.pk) if mode=='all' else []
            audit('catalogue_visibility_changed',request.user.pk,mode=mode,catalogue_revision=config.catalogue_revision,archived=archived,restored=restored,jobs=jobs,manual_fulfilment=True)
        return Response({**summary,'preview':False,'archived':archived,'restored':restored,'jobs':jobs,'revision':config.catalogue_revision})
