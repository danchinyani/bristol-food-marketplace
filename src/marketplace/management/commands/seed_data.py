from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from marketplace.models import (
    Producer, Customer, Product, Recipe,
    CustomerOrder, OrderItem, BasketItem,
    RecurringOrder, RecurringOrderItem, RecurringOrderUpcomingItem,
    Notification, ProductReview
)


class Command(BaseCommand):
    help = 'Seeds the database with test data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')

        # CREATE SUPERUSER
        if not User.objects.filter(username='admin1').exists():
            User.objects.create_superuser('admin1', 'admin@brfn.com', 'admin123')
            self.stdout.write('Created superuser: admin1 / admin123')
        else:
            self.stdout.write('Superuser already exists: admin1')

        # CREATE PRODUCER
        if not User.objects.filter(username='prod1').exists():
            prod_user = User.objects.create_user(
                username='prod1',
                password='producer1',
                email='prod1@brfn.com'
            )
            producer = Producer.objects.create(
                user=prod_user,
                business_name='Bristol Valley Farm',
                contact_name='Jane Smith',
                email='prod1@brfn.com',
                phone_number='+441179123456',
                business_address='1 Valley Road, Bristol',
                postcode='BS14DJ',
                bio='We are a family-run farm producing fresh organic vegetables in the heart of Bristol.'
            )
            self.stdout.write('Created producer: prod1 / producer1')
        else:
            producer = Producer.objects.get(user__username='prod1')
            self.stdout.write('Producer already exists: prod1')

        # CREATE SECOND PRODUCER FOR MULTI-VENDOR TESTING
        if not User.objects.filter(username='prod2').exists():
            prod_user2 = User.objects.create_user(
                username='prod2',
                password='producer1',
                email='prod2@brfn.com'
            )
            producer2 = Producer.objects.create(
                user=prod_user2,
                business_name='Hillside Dairy',
                contact_name='John Hill',
                email='prod2@brfn.com',
                phone_number='+441179654321',
                business_address='2 Hillside Lane, Bristol',
                postcode='BS27AB',
                bio='Award-winning dairy farm supplying fresh milk, cheese and eggs to Bristol.'
            )
            self.stdout.write('Created producer: prod2 / producer1')
        else:
            producer2 = Producer.objects.get(user__username='prod2')
            self.stdout.write('Producer already exists: prod2')

        # CREATE CUSTOMER
        if not User.objects.filter(username='cust1').exists():
            cust_user = User.objects.create_user(
                username='cust1',
                password='customer1',
                email='cust1@email.com'
            )
            customer = Customer.objects.create(
                user=cust_user,
                name='Robert Johnson',
                email='cust1@email.com',
                phone_number='+447700900123',
                address='45 Park Street, Bristol',
                postcode='BS15JG',
            )
            self.stdout.write('Created customer: cust1 / customer1')
        else:
            customer = Customer.objects.get(user__username='cust1')
            self.stdout.write('Customer already exists: cust1')

        # CREATE PRODUCTS
        products_data = [
            {
                'producer': producer,
                'name': 'Organic Carrots',
                'description': 'Fresh organic carrots grown in Bristol Valley. Perfect for soups and salads.',
                'price': '1.50',
                'unit': 'per kg',
                'stock_quantity': 50,
                'is_organic': True,
                'allergens': [],
                'category': 'VEG',
            },
            {
                'producer': producer,
                'name': 'Organic Tomatoes',
                'description': 'Juicy organic tomatoes freshly picked from our greenhouse.',
                'price': '2.00',
                'unit': 'per kg',
                'stock_quantity': 30,
                'is_organic': True,
                'allergens': [],
                'category': 'VEG',
            },
            {
                'producer': producer,
                'name': 'Free Range Eggs',
                'description': 'Fresh eggs from free-range hens, collected daily.',
                'price': '3.50',
                'unit': 'per dozen',
                'stock_quantity': 40,
                'is_organic': True,
                'allergens': ['EGGS'],
                'category': 'DAIRY',
            },
            {
                'producer': producer,
                'name': 'Organic Potatoes',
                'description': 'Freshly dug organic potatoes, perfect for roasting.',
                'price': '1.20',
                'unit': 'per kg',
                'stock_quantity': 60,
                'is_organic': True,
                'allergens': [],
                'category': 'VEG',
            },
            {
                'producer': producer2,
                'name': 'Fresh Milk',
                'description': 'Full fat fresh milk from our Hillside herd, pasteurised daily.',
                'price': '1.20',
                'unit': 'per litre',
                'stock_quantity': 40,
                'is_organic': False,
                'allergens': ['MILK'],
                'category': 'DAIRY',
            },
            {
                'producer': producer2,
                'name': 'Cheddar Cheese',
                'description': 'Mature cheddar cheese made from our own herd\'s milk.',
                'price': '4.50',
                'unit': 'per 250g',
                'stock_quantity': 20,
                'is_organic': False,
                'allergens': ['MILK'],
                'category': 'DAIRY',
            },
            {
                'producer': producer2,
                'name': 'Natural Yoghurt',
                'description': 'Creamy natural yoghurt made from fresh local milk.',
                'price': '2.00',
                'unit': 'per 500g',
                'stock_quantity': 25,
                'is_organic': False,
                'allergens': ['MILK'],
                'category': 'DAIRY',
            },
            {
                'producer': producer2,
                'name': 'Walnut Bread',
                'description': 'Freshly baked walnut bread using locally milled flour.',
                'price': '3.00',
                'unit': 'per loaf',
                'stock_quantity': 12,
                'is_organic': False,
                'allergens': ['GLUTEN', 'NUTS'],
                'category': 'BAKERY',
            },
        ]

        created_products = []
        for p in products_data:
            if not Product.objects.filter(name=p['name'], producer=p['producer']).exists():
                product = Product.objects.create(
                    producer=p['producer'],
                    name=p['name'],
                    description=p['description'],
                    price=p['price'],
                    unit=p['unit'],
                    stock_quantity=p['stock_quantity'],
                    is_organic=p['is_organic'],
                    allergens=p['allergens'],
                    category=p['category'],
                    low_stock_threshold=10,
                )
                created_products.append(product)
                self.stdout.write(f'Created product: {p["name"]}')
            else:
                created_products.append(
                    Product.objects.get(name=p['name'], producer=p['producer'])
                )
                self.stdout.write(f'Product already exists: {p["name"]}')

        # CREATE RECIPES
        recipes_data = [
            {
                'producer': producer,
                'title': 'Roasted Root Vegetable Medley',
                'description': 'A delicious autumn recipe using fresh seasonal vegetables from the farm.',
                'ingredients': 'Organic Carrots - 500g\nOrganic Potatoes - 400g\nOlive oil - 2 tbsp\nRosemary - 1 sprig\nSalt and pepper to taste',
                'instructions': '1. Preheat oven to 200C.\n2. Peel and chop all vegetables into chunks.\n3. Toss with olive oil, rosemary, salt and pepper.\n4. Spread on a baking tray.\n5. Roast for 35-40 minutes until golden.',
                'seasonal_tag': 'AUTUMN',
            },
            {
                'producer': producer,
                'title': 'Simple Tomato Salad',
                'description': 'A quick and refreshing summer salad using fresh organic tomatoes.',
                'ingredients': 'Organic Tomatoes - 4 large\nBasil - handful\nOlive oil - 1 tbsp\nBalsamic vinegar - 1 tsp\nSalt and pepper',
                'instructions': '1. Slice tomatoes and arrange on a plate.\n2. Scatter fresh basil leaves.\n3. Drizzle with olive oil and balsamic.\n4. Season and serve immediately.',
                'seasonal_tag': 'SUMMER',
            },
            {
                'producer': producer2,
                'title': 'Cheesy Scrambled Eggs',
                'description': 'Creamy scrambled eggs with melted cheddar, perfect for breakfast.',
                'ingredients': 'Free Range Eggs - 3\nCheddar Cheese - 30g grated\nFresh Milk - 2 tbsp\nButter - 1 tsp\nSalt and pepper',
                'instructions': '1. Whisk eggs with milk, salt and pepper.\n2. Melt butter in a pan over low heat.\n3. Add egg mixture and stir slowly.\n4. Add cheese just before eggs set.\n5. Serve immediately.',
                'seasonal_tag': 'ALL',
            },
        ]

        for r in recipes_data:
            if not Recipe.objects.filter(title=r['title'], producer=r['producer']).exists():
                recipe = Recipe.objects.create(
                    producer=r['producer'],
                    title=r['title'],
                    description=r['description'],
                    ingredients=r['ingredients'],
                    instructions=r['instructions'],
                    seasonal_tag=r['seasonal_tag'],
                )
                if producer.products.exists():
                    recipe.linked_products.set(list(producer.products.all()[:2]))
                self.stdout.write(f'Created recipe: {r["title"]}')
            else:
                recipe = Recipe.objects.get(title=r['title'], producer=r['producer'])
                if not recipe.linked_products.exists():
                    if r['producer'] == producer:
                        recipe.linked_products.set(list(producer.products.all()[:2]))
                    else:
                        recipe.linked_products.set(list(producer2.products.all()[:2]))
                self.stdout.write(f'Recipe already exists: {r["title"]}')

        # CREATE PAST ORDERS FOR CUSTOMER
        if created_products and not CustomerOrder.objects.filter(customer=customer).exists():
            # ORDER 1 - DELIVERED
            order1 = CustomerOrder.objects.create(
                customer=customer,
                delivery_address='45 Park Street, Bristol, BS1 5JG',
                preferred_delivery_date=date.today() - timedelta(days=14),
                card_holder_name='Robert Johnson',
                card_number_last4='1234',
                total_price=Decimal('7.00'),
                status='DELIVERED',
            )
            OrderItem.objects.create(
                order=order1,
                product=created_products[0],  # Organic Carrots
                quantity=2,
                unit_price=Decimal('1.50'),
            )
            OrderItem.objects.create(
                order=order1,
                product=created_products[1],  # Organic Tomatoes
                quantity=2,
                unit_price=Decimal('2.00'),
            )
            self.stdout.write('Created past order #1 (DELIVERED)')

            # ORDER 2 - DELIVERED
            order2 = CustomerOrder.objects.create(
                customer=customer,
                delivery_address='45 Park Street, Bristol, BS1 5JG',
                preferred_delivery_date=date.today() - timedelta(days=7),
                card_holder_name='Robert Johnson',
                card_number_last4='1234',
                total_price=Decimal('9.70'),
                status='DELIVERED',
            )
            OrderItem.objects.create(
                order=order2,
                product=created_products[4],  # Fresh Milk
                quantity=3,
                unit_price=Decimal('1.20'),
            )
            OrderItem.objects.create(
                order=order2,
                product=created_products[5],  # Cheddar Cheese
                quantity=1,
                unit_price=Decimal('4.50'),
            )
            OrderItem.objects.create(
                order=order2,
                product=created_products[2],  # Free Range Eggs
                quantity=1,
                unit_price=Decimal('3.50'),
            )
            self.stdout.write('Created past order #2 (DELIVERED)')

            # ORDER 3 - PENDING
            order3 = CustomerOrder.objects.create(
                customer=customer,
                delivery_address='45 Park Street, Bristol, BS1 5JG',
                preferred_delivery_date=date.today() + timedelta(days=3),
                card_holder_name='Robert Johnson',
                card_number_last4='1234',
                total_price=Decimal('5.70'),
                status='CONFIRMED',
            )
            OrderItem.objects.create(
                order=order3,
                product=created_products[3],  # Organic Potatoes
                quantity=2,
                unit_price=Decimal('1.20'),
            )
            OrderItem.objects.create(
                order=order3,
                product=created_products[6],  # Natural Yoghurt
                quantity=1,
                unit_price=Decimal('2.00'),
            )
            self.stdout.write('Created upcoming order #3 (CONFIRMED)')
        else:
            self.stdout.write('Orders already exist for cust1')

        # FETCH ORDERS/ITEMS FOR FOLLOW-UP SEED DATA
        delivered_order = CustomerOrder.objects.filter(
            customer=customer,
            status='DELIVERED',
        ).order_by('preferred_delivery_date').first()

        # CREATE BASKET ITEMS
        if not BasketItem.objects.filter(customer=customer).exists() and len(created_products) >= 2:
            BasketItem.objects.create(customer=customer, product=created_products[0], quantity=1)
            BasketItem.objects.create(customer=customer, product=created_products[4], quantity=2)
            self.stdout.write('Created basket items for cust1')
        else:
            self.stdout.write('Basket items already exist for cust1')

        # CREATE RECURRING ORDER + TEMPLATE ITEMS
        recurring_order = RecurringOrder.objects.filter(customer=customer).first()
        if recurring_order is None:
            recurring_order = RecurringOrder.objects.create(
                customer=customer,
                frequency='WEEKLY',
                recurrence_day=0,
                delivery_week_offset=0,
                delivery_day=2,
                delivery_address='45 Park Street, Bristol, BS1 5JG',
                next_order_date=date.today() + timedelta(days=7),
                status='ACTIVE',
            )

            if len(created_products) >= 2:
                RecurringOrderItem.objects.create(
                    recurring_order=recurring_order,
                    product=created_products[0],
                    quantity=2,
                )
                RecurringOrderItem.objects.create(
                    recurring_order=recurring_order,
                    product=created_products[1],
                    quantity=1,
                )

                RecurringOrderUpcomingItem.objects.create(
                    recurring_order=recurring_order,
                    product=created_products[0],
                    scheduled_for=recurring_order.next_order_date,
                    quantity=3,
                )

            self.stdout.write('Created recurring order template and next-order override')
        else:
            if not recurring_order.items.exists() and len(created_products) >= 2:
                RecurringOrderItem.objects.create(
                    recurring_order=recurring_order,
                    product=created_products[0],
                    quantity=2,
                )
                RecurringOrderItem.objects.create(
                    recurring_order=recurring_order,
                    product=created_products[1],
                    quantity=1,
                )

            if not recurring_order.upcoming_items.filter(scheduled_for=recurring_order.next_order_date).exists() and len(created_products) >= 1:
                RecurringOrderUpcomingItem.objects.create(
                    recurring_order=recurring_order,
                    product=created_products[0],
                    scheduled_for=recurring_order.next_order_date,
                    quantity=3,
                )

            self.stdout.write('Recurring order already exists for cust1')

        # CREATE SAMPLE REVIEW
        if delivered_order:
            review_target_item = delivered_order.items.first()
            if review_target_item and not ProductReview.objects.filter(order_item=review_target_item).exists():
                ProductReview.objects.create(
                    customer=customer,
                    product=review_target_item.product,
                    order_item=review_target_item,
                    rating=5,
                    comment='Excellent quality produce and very fresh.',
                    is_anonymous=False,
                )
                self.stdout.write('Created sample product review')
            else:
                self.stdout.write('Sample product review already exists')

        # CREATE SAMPLE NOTIFICATIONS
        if not Notification.objects.filter(user=customer.user).exists():
            Notification.objects.create(
                user=customer.user,
                message='Welcome to BRFN! Your account has been seeded with sample data.',
                is_read=False,
            )
            self.stdout.write('Created customer notification')
        else:
            self.stdout.write('Customer notifications already exist')

        if not Notification.objects.filter(user=producer.user).exists():
            Notification.objects.create(
                user=producer.user,
                message='You have a new sample order waiting for fulfilment.',
                is_read=False,
            )
            self.stdout.write('Created producer notification')
        else:
            self.stdout.write('Producer notifications already exist')

        self.stdout.write(self.style.SUCCESS('\nDone! Test accounts:'))
        self.stdout.write('  Admin:    admin1 / admin123')
        self.stdout.write('  Producer: prod1 / producer1')
        self.stdout.write('  Producer: prod2 / producer1')
        self.stdout.write('  Customer: cust1 / customer1')