from rest_framework import serializers
from .models import Item, Cart, Customer, NewOrder

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = '__all__'


class CartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cart
        fields = '__all__'


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'


class CustomerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['fullName', 'gender', 'division', 'district', 'thana', 'union', 'village']

    def update(self, instance, validated_data):
        # Exclude 'username' and 'password' fields from the update
        validated_data.pop('username', None)
        validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
    