from django.contrib import admin
from .models import Item, Customer, Order, Ordered, Canceled, OrderDetail, Transaction

admin.site.register(Customer)
admin.site.register(Item)
admin.site.register(Order)
admin.site.register(Ordered)
admin.site.register(Canceled)
admin.site.register(OrderDetail)
admin.site.register(Transaction)


def completed_button(self, obj):
        if obj.pk:
            move_url = reverse('move_completed_orders', args=[obj.pk])
            return format_html(
                '<div id="move_button"><a class="button move_button" href="{}" target="_blank">Move</a></div><div style="margin-top: 10px; color: red; margin-left:5px; display:none" id="snackbar_container_{}">Error !</div>',
                move_url, obj.pk
            )
        else:
            return '-'

    # completed_button.short_description = "Actions" def move_completed_orders(request, pk):
