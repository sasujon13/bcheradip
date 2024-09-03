from django.shortcuts import render, get_object_or_404
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .models import Item, Customer, Order, OrderDetail, Transaction, Ordered, Canceled
from .serializers import ItemSerializer, CustomerSerializer, CustomerUpdateSerializer, OrderSerializer, NotificationSerializer
from .permissions import IsSuperUserOrStaff, PublicAccess
from .location import Bangladesh
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
import logging, random, string, json  
from django.conf import settings


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
            
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        # Update image URLs to include 'manage' prefix
        for item_data in response.data:
            if 'image' in item_data and item_data['image']:
                item_data['image'] = f'{settings.HOST_URL}/manage/media/{item_data["image"].split("/media/")[-1]}'

        return response

@api_view(['GET'])
@permission_classes([IsSuperUserOrStaff])
def item_list(request):
    items = Item.objects.all()
    serializer = ItemSerializer(items, many=True)
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
                if hasattr(user, 'acctype'):acctype = user.acctype
                else:acctype = None
                if hasattr(user, 'fullName'):fullName = user.fullName
                else:fullName = None
                if hasattr(user, 'group'):group = user.group
                else:group = None
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
                return Response({'authToken': token, 'acctype': acctype, 'fullName': fullName, 'group': group, 'gender': gender, 'division': division, 'district': district, 'thana': thana, 'union': union, 'village': village}, status=status.HTTP_200_OK)
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
    serializer_class = OrderSerializer
    lookup_field = 'username'

    def get_object(self):
        username = self.kwargs['username']
        try:
            return Order.objects.filter(username=username)
        except Order.DoesNotExist:
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


class NotificationExistsView(APIView):
    def get(self, request, *args, **kwargs):
        notification = Notification.objects.all()
        serializer = NotificationSerializer(notification, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)


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
                    
                    new_order = Order(**json_data)
                    new_order.save()
                    new_order.transaction.add(transaction)
                    
                    for detail_data in order_details_data:
                        logger.debug(detail_data)
                        order_detail = OrderDetail.objects.create(**detail_data)
                        new_order.orderDetails.add(order_detail)
                        
                    transaction.username = username 
                    transaction.save()

                    return JsonResponse({'message': 'Order Created Successfully'})
                else:
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



class MobileUpdateView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        newusername = request.data.get('newusername')
        password = request.data.get('password')
        user = Customer.objects.get(username=username, password=password)
        if user is not None:
            user.username = newusername 
            user.save()
            token = self.generate_unique_key()
            return Response({'authToken': token}, status=status.HTTP_200_OK)
        

    def generate_unique_key(self):
        length = 40
        characters = string.ascii_letters + string.digits
        key = ''.join(random.choice(characters) for _ in range(length))
        return key 



def view_order(request, pk):
    order = get_object_or_404(Order, pk=pk)
    # Render the 'view_order.html' template with the order details
    return render(request, 'cheradip/view_order.html', {'order': order})


def view_ordered(request, pk):
    order = get_object_or_404(Ordered, pk=pk)
    # Render the 'view_order.html' template with the order details
    return render(request, 'cheradip/view_order.html', {'order': order})


def view_canceled(request, pk):
    order = get_object_or_404(Canceled, pk=pk)
    # Render the 'view_order.html' template with the order details
    return render(request, 'cheradip/view_order.html', {'order': order})


def update_shipped_status(request, order_id, is_shipped):
    try:
        # Get the Order instance by order_id
        order = get_object_or_404(Order, id=order_id)

        # Convert the 'is_shipped' string to a boolean
        is_shipped = is_shipped.lower() == 'true'

        # Update the 'shipped' field in the database
        order.shipped = is_shipped
        order.save()

        # Assuming the update was successful
        response_data = {"updated": True}
        return JsonResponse(response_data)
    except Exception as e:
        # Handle any exceptions or errors
        response_data = {"error": str(e)}
        return JsonResponse(response_data, status=500)
    

def move_completed_orders(request, pk):
    completed_orders = Order.objects.filter(shipped=True, pk=pk)

    for new_order in completed_orders:
        order = Ordered.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())

        for order_detail in order.orderDetails.all():
            try:
                item = Item.objects.get(id=order_detail.id)  # Retrieve the correct Item
                item.in_stock -= order_detail.Quantity 
                item.save()
            except Item.DoesNotExist:
                # Print or log the problematic OrderDetail
                print(f"Item not found for OrderDetail: {order_detail.Name}")


        new_order.delete()

        message = "Completed Orders moved successfully"
        return HttpResponse(message)
    message = "Sorry! First check the Shipping Status and then Move again!"
    return HttpResponse(message)

def move_canceled_orders(request, pk):
    canceled_orders = Order.objects.filter(pk=pk)

    for new_order in canceled_orders:
        order = Canceled.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())

        new_order.delete()

        message = "Canceled Orders moved successfully"
        return HttpResponse(message)
    message = "Sorry! First check the Shipping Status and then Move again!"
    return HttpResponse(message)


def retrieve_canceled_orders(request, pk):
    canceled_orders = Canceled.objects.filter(pk=pk)

    for new_order in canceled_orders:
        order = Order.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())

        new_order.delete()

        message = "Canceled Ordered retrieved successfully"
        return HttpResponseRedirect('/admin/cheradip/canceled/')
    message = "Sorry! Canceled Ordered failed to retrieve!"
    return HttpResponse(message)


def retrieve_ordered_orders(request, pk):
    ordered_orders = Ordered.objects.filter(pk=pk)

    for new_order in ordered_orders:
        order = Order.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        # Transfer many-to-many relations
        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())
        
        for order_detail in order.orderDetails.all():
            try:
                item = Item.objects.get(id=order_detail.id)  # Retrieve the correct Item
                item.in_stock += order_detail.Quantity 
                item.save()
            except Item.DoesNotExist:
                # Print or log the problematic OrderDetail
                print(f"Item not found for OrderDetail: {order_detail.Name}")

        new_order.delete()

        message = "Ordered Orders retrieved successfully"
        return HttpResponseRedirect('/admin/cheradip/ordered/')
    message = "Sorry! Ordered Orders failed retrieve!"
    return HttpResponse(message)



def get_shipped_status(request, order_id):
    try:
        # Fetch the Order record by its ID
        new_order = Order.objects.get(pk=order_id)
        shipped = new_order.shipped
        return JsonResponse({'shipped': shipped})
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)