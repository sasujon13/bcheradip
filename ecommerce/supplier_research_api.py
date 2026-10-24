from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from .permissions import IsCommerceAdmin
from .views import CommerceAdminAuthMixin
from .models import Supplier, SupplierResearchBatch, SupplierResearchItem
from .supplier_api import require
from .supplier_research import start, update, snapshot


class Checkpoint(serializers.Serializer):
    id=serializers.IntegerField(min_value=1)
    note=serializers.CharField(max_length=6000,allow_blank=True)


class Input(serializers.Serializer):
    action=serializers.ChoiceField(choices=['start','pause','resume','save','finish'])
    batch_id=serializers.UUIDField(required=False)
    item_id=serializers.IntegerField(min_value=1,required=False)
    supplier_ids=serializers.ListField(child=serializers.IntegerField(min_value=1),max_length=100,required=False)
    size=serializers.IntegerField(min_value=1,max_value=10,default=3)
    note=serializers.CharField(max_length=6000,allow_blank=True,required=False)
    checkpoints=Checkpoint(many=True,required=False,max_length=10)


class SupplierResearchView(CommerceAdminAuthMixin,APIView):
    permission_classes=[IsCommerceAdmin]
    permission_model=Supplier
    permission_requirements={'POST':((Supplier,'view'),)}

    def get(self,request):
        require(request.user,'research_supplier')
        return Response({'batch':snapshot(SupplierResearchBatch.objects.using('ecommerce').first()),
                         'automatic_research':False,'quota_access':False})

    def post(self,request):
        require(request.user,'research_supplier')
        data=Input(data=request.data);data.is_valid(raise_exception=True);value=data.validated_data
        try:
            if value['action']=='start':
                batch=start(request.user.pk,value.get('supplier_ids'),value['size'])
            else:
                if 'batch_id' not in value or (value['action'] in ('save','finish') and 'item_id' not in value):
                    raise ValueError('Select the saved batch and research item.')
                batch=update(request.user.pk,value['batch_id'],value['action'],value.get('item_id'),value.get('note'),value.get('checkpoints'))
        except (ValueError,SupplierResearchBatch.DoesNotExist,SupplierResearchItem.DoesNotExist) as exc:
            raise ValidationError(str(exc))
        return Response({'batch':snapshot(batch)})
