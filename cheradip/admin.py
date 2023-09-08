from django.contrib import admin
from .models import Item, Customer, Cart, Order, NewOrder, OrderDetail

admin.site.register(Customer)
admin.site.register(Item)
admin.site.register(Cart)
admin.site.register(Order)
admin.site.register(NewOrder)
admin.site.register(OrderDetail)
