from django.contrib import admin
from .models import Producer, Customer, Product, BasketItem, CustomerOrder, OrderItem, FarmStory

admin.site.register(Producer)
admin.site.register(Customer)
admin.site.register(Product)
admin.site.register(BasketItem)
admin.site.register(CustomerOrder)
admin.site.register(OrderItem)
admin.site.register(FarmStory)
