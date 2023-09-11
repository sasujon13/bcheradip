from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .models import Cart, Item, Customer, NewOrder, OrderDetail, Transaction
from .serializers import CartSerializer, ItemSerializer, CustomerSerializer, CustomerUpdateSerializer, NewOrderSerializer
from .permissions import IsSuperUserOrStaff, PublicAccess
from .location import Bangladesh
from django.http import Http404, JsonResponse
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
import logging, random, string, json  


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ItemListCreateView(generics.ListCreateAPIView):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer

    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [PublicAccess()]
        else:
            return [IsSuperUserOrStaff()]

@api_view(['GET'])
@permission_classes([IsSuperUserOrStaff])
def item_list(request):
    items = Item.objects.all()
    serializer = ItemSerializer(items, many=True)
    return Response(serializer.data) 


class CartListCreateView(generics.ListCreateAPIView):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer

    def get_permissions(self):
            return [PublicAccess()]

@api_view(['GET'])
@permission_classes([PublicAccess])
def cart(request):
    cart = Cart.objects.all()
    serializer = CartSerializer(cart, many=True)
    return Response(serializer.data) 


class DivisionsView(APIView):
    def get(self, request):
        divisions = list(Bangladesh.keys())
        return Response(divisions)


class DistrictsView(APIView):
    def get(self, request):
        division = request.query_params.get('division')
        if division in Bangladesh:
            districts = list(Bangladesh[division].keys())
            return Response(districts)
        return Response([])


class ThanasView(APIView):
    def get(self, request):
        division = request.query_params.get('division')
        district = request.query_params.get('district')
        if division in Bangladesh and district in Bangladesh[division]:
            thanas = Bangladesh[division][district]
            return Response(thanas)
        return Response([])


class CustomerCreateView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            token = self.generate_unique_key()
            return Response({'authToken': token}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def generate_unique_key(self):
            length = 40
            characters = string.ascii_letters + string.digits
            key = ''.join(random.choice(characters) for _ in range(length))
            return key 

class CustomerRetrieveView(APIView):
    def post(self, request, *args, **kwargs):
            username = request.data.get('username')
            password = request.data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                if hasattr(user, 'fullName'):fullName = user.fullName
                else:fullName = None
                if hasattr(user, 'gender'):gender = user.gender
                else:gender = None
                if hasattr(user, 'division'):division = user.division
                else:division = None 
                if hasattr(user, 'district'): district = user.district
                else:district = None
                if hasattr(user, 'thana'):thana = user.thana
                else:thana = None
                if hasattr(user, 'union'):union = user.union
                else:union = None
                if hasattr(user, 'village'):village = user.village
                else:village = None
                token = self.generate_unique_key()
                return Response({'authToken': token, 'username': username, 'fullName': fullName, 'gender': gender, 'division': division, 'district': district, 'thana': thana, 'union': union, 'village': village}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


    def generate_unique_key(self):
            length = 40
            characters = string.ascii_letters + string.digits
            key = ''.join(random.choice(characters) for _ in range(length))
            return key 
    

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            customer_data = {
                'username': request.user.username, 
                'fullName': request.user.full_name,  
            }
            return Response(customer_data, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)



class OrderRetrieveView(generics.RetrieveAPIView):
    serializer_class = NewOrderSerializer
    lookup_field = 'username'

    def get_object(self):
        username = self.kwargs['username']
        try:
            return NewOrder.objects.filter(username=username)
        except NewOrder.DoesNotExist:
            raise Http404

    def get(self, request, *args, **kwargs):
        instances = self.get_object()
        if instances.exists():
            serializer = self.get_serializer(instances, many=True)
            return Response(serializer.data)
        else:
            return Response("0 orders")
        

class CustomerUpdateView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            serializer = CustomerUpdateSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                token = self.generate_unique_key()
                return Response({'authToken': token}, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def generate_unique_key(self):
            length = 40
            characters = string.ascii_letters + string.digits
            key = ''.join(random.choice(characters) for _ in range(length))
            return key 

class CustomerResetView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            serializer = CustomerSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MobileNumberExistsView(APIView):
    def get(self, request, *args, **kwargs):
        username = request.query_params.get('username')
        
        try:
            exists = Customer.objects.filter(username=username).exists()
        except Customer.DoesNotExist:
            exists = False
        
        return Response({'exists': exists}, status=status.HTTP_200_OK)


class PasswordExistsView(APIView):
    def get(self, request, *args, **kwargs):
        username = request.query_params.get('username')
        password = request.query_params.get('password')
        
        try:
            customer = Customer.objects.get(username=username)
            
            if(customer.password == password):
                exists = True
            else:
                exists = False
        except Customer.DoesNotExist:
            exists = False
        return Response({'exists': exists}, status=status.HTTP_200_OK)
    

@csrf_exempt
def save_json_data(request):
    if request.method == 'POST':
        try:
            json_data = json.loads(request.body.decode('utf-8'))
            order_details_data = json_data.pop('orderDetails', [])
            trxid = json_data.pop('trxid', None)
            paidFrom = json_data.pop('paidFrom', None)
            username = json_data.get('username', None)
            
            try:
                transaction = Transaction.objects.get(trxid=trxid, paidFrom=paidFrom)
            except Transaction.DoesNotExist:
                transaction = None
            
            if transaction:
                if username != transaction.username:
                    transaction.username = username 
                    transaction.save()
                
                    new_order = NewOrder(**json_data)
                    new_order.save()
                    new_order.transaction.add(transaction)
                    
                    for detail_data in order_details_data:
                        order_detail = OrderDetail.objects.create(**detail_data)
                        new_order.orderDetails.add(order_detail)

                    return JsonResponse({'message': 'Order Created Successfully'})
                return JsonResponse({'message': 'You already have an Order with this TrxId!'})
            else:
                return JsonResponse({'error': 'Your TrxId / Account has not been found! Please Check your TrxId and Account Number, Or Contact Us'})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    else:
        return JsonResponse({'message': 'Invalid request method'}, status=405)


class PasswordUpdateView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        newpassword = request.data.get('newpassword')
        user = Customer.objects.get(username=username, password=password)
        if user is not None:
            user.password = newpassword 
            user.save()
            token = self.generate_unique_key()
            return Response({'authToken': token}, status=status.HTTP_200_OK)
        

    def generate_unique_key(self):
        length = 40
        characters = string.ascii_letters + string.digits
        key = ''.join(random.choice(characters) for _ in range(length))
        return key 