from django.contrib import admin
from .models import Producer, Customer, Product, BasketItem, CustomerOrder, OrderItem

admin.site.register(Producer)
admin.site.register(Customer)
admin.site.register(Product)
admin.site.register(BasketItem)
admin.site.register(CustomerOrder)
admin.site.register(OrderItem)