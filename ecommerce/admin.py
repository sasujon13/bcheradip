from django.contrib import admin

from .models import (
    Brand, Cart, CartItem, Category, CommerceNotification, Coupon, ImportJob,
    InventoryMovement, Order, OrderItem, OrderStatusHistory, Payment, Product,
    ProductImage, ProductVariant, Review, Shipment,
)


for model in (
    Category, Brand, Product, ProductVariant, ProductImage, InventoryMovement,
    Cart, CartItem, Coupon, Order, OrderItem, Payment, Shipment,
    OrderStatusHistory, Review, CommerceNotification, ImportJob,
):
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass

