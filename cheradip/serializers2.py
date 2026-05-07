from rest_framework import serializers
from .models import Institutes, Item, Token, Merit, Merit5, Recommend, Banbeis, Customer, Order, Ordered, OrderDetail, Transaction, Notification, Vacancy6, Vacancy5

class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = '__all__'

class InstitutesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institutes
        fields = '__all__'

class RecommendSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recommend
        fields = '__all__'

class BanbeisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banbeis
        fields = '__all__'

class VacancySerializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy6
        fields = '__all__'

class MeritSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merit
        fields = '__all__'

class Vacancy5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy5
        fields = '__all__'

class Merit5Serializer(serializers.ModelSerializer):
    class Meta:
        model = Merit5
        fields = '__all__'

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'


class CustomerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['acctype', 'fullName', 'group', 'gender', 'division', 'district', 'thana', 'union', 'village']

    def update(self, instance, validated_data):
        # Exclude 'username' and 'password' fields from the update
        validated_data.pop('username', None)
        validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class OrderDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderDetail
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):
    orderDetails = OrderDetailSerializer(many=True, read_only=True)
    transaction = TransactionSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = '__all__'   

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'text', 'link']