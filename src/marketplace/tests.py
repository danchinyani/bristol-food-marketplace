from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from datetime import date, timedelta

from .forms import CheckoutForm, build_delivery_day_choices
from .models import Customer, Producer, Product, BasketItem, CustomerOrder, Notification, RecurringOrder, RecurringOrderUpcomingItem, FarmStory
from .tasks import process_due_recurring_orders


class AddProductViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='producer1', password='testpass123')
        self.other_user = User.objects.create_user(username='producer2', password='testpass123')

        self.producer = Producer.objects.create(
            user=self.user,
            business_name='Green Farm',
            contact_name='Alice Grower',
            email='alice@example.com',
            business_address='1 Market Lane',
            postcode='BS11AA'
        )
        self.other_producer = Producer.objects.create(
            user=self.other_user,
            business_name='River Farm',
            contact_name='Bob Grower',
            email='bob@example.com',
            business_address='2 River Street',
            postcode='BS22BB'
        )

    def test_add_product_page_shows_only_logged_in_producer_products(self):
        own_product = Product.objects.create(
            producer=self.producer,
            name='Carrots',
            category='VEG',
            description='Fresh carrots',
            price='2.50',
            unit='per kg',
            stock_quantity=10,
            is_organic=True,
            image='products/carrots.jpg',
        )
        Product.objects.create(
            producer=self.other_producer,
            name='Milk',
            category='DAIRY',
            description='Fresh milk',
            price='1.80',
            unit='per bottle',
            stock_quantity=5,
            is_organic=False
        )

        self.client.login(username='producer1', password='testpass123')
        response = self.client.get(reverse('add_product'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_product.name)
        self.assertContains(response, own_product.image.url)
        self.assertContains(response, 'Image of Carrots')
        self.assertNotContains(response, 'River Farm')
        self.assertEqual(list(response.context['producer_products']), [own_product])

    def test_add_product_post_redirects_back_to_add_product(self):
        self.client.login(username='producer1', password='testpass123')

        response = self.client.post(
            reverse('add_product'),
            {
                'name': 'Apples',
                'category': 'FRUIT',
                'description': 'Sweet apples',
                'price': '3.25',
                'unit': 'per kg',
                'stock_quantity': 12,
                'is_organic': 'on',
                'seasonal_from': 'SPRING',
                'seasonal_to': 'WINTER',
                'discount_percent': 0,
                'allergens': [],
            }
        )

        self.assertRedirects(response, reverse('add_product'))
        self.assertTrue(Product.objects.filter(name='Apples', producer=self.producer).exists())

    def test_product_actions_page_only_allows_product_owner(self):
        owned_product = Product.objects.create(
            producer=self.producer,
            name='Spinach',
            category='VEG',
            description='Fresh spinach',
            price='2.10',
            unit='per bunch',
            stock_quantity=9,
            is_organic=True
        )
        other_product = Product.objects.create(
            producer=self.other_producer,
            name='Cheese',
            category='DAIRY',
            description='Local cheese',
            price='4.20',
            unit='per block',
            stock_quantity=6,
            is_organic=False
        )

        self.client.login(username='producer1', password='testpass123')
        owned_response = self.client.get(reverse('producer_product_actions', args=[owned_product.id]))
        forbidden_response = self.client.get(reverse('producer_product_actions', args=[other_product.id]))

        self.assertEqual(owned_response.status_code, 200)
        self.assertEqual(forbidden_response.status_code, 404)

    def test_edit_product_updates_database_record(self):
        product = Product.objects.create(
            producer=self.producer,
            name='Tomatoes',
            category='VEG',
            description='Juicy tomatoes',
            price='2.95',
            unit='per kg',
            stock_quantity=13,
            is_organic=False
        )

        self.client.login(username='producer1', password='testpass123')
        response = self.client.post(
            reverse('edit_product', args=[product.id]),
            {
                'name': 'Cherry Tomatoes',
                'category': 'VEG',
                'description': 'Small sweet tomatoes',
                'price': '3.40',
                'unit': 'per kg',
                'stock_quantity': 17,
                'is_organic': 'on',
                'seasonal_from': 'SUMMER',
                'seasonal_to': 'AUTUMN',
                'discount_percent': 0,
                'allergens': [],
            }
        )

        product.refresh_from_db()
        self.assertRedirects(response, reverse('add_product'))
        self.assertEqual(product.name, 'Cherry Tomatoes')
        self.assertEqual(str(product.price), '3.40')
        self.assertTrue(product.is_organic)

    def test_delete_product_removes_database_record(self):
        product = Product.objects.create(
            producer=self.producer,
            name='Potatoes',
            category='VEG',
            description='Earthy potatoes',
            price='1.60',
            unit='per kg',
            stock_quantity=22,
            is_organic=False
        )

        self.client.login(username='producer1', password='testpass123')
        response = self.client.post(reverse('delete_product', args=[product.id]))

        self.assertRedirects(response, reverse('add_product'))
        self.assertFalse(Product.objects.filter(id=product.id).exists())


class CustomerMarketViewTests(TestCase):
    def setUp(self):
        self.producer_user = User.objects.create_user(username='producer_market', password='testpass123')
        self.customer_user = User.objects.create_user(username='customer_market', password='testpass123')

        self.producer = Producer.objects.create(
            user=self.producer_user,
            business_name='Hilltop Farm',
            contact_name='Farmer Hill',
            email='hill@example.com',
            business_address='10 Hill Road',
            postcode='BS33CC'
        )
        self.customer = Customer.objects.create(
            user=self.customer_user,
            name='Chris Buyer',
            email='buyer@example.com',
            address='5 City Street',
            postcode='BS44DD'
        )

    def test_customer_market_shows_products_and_producer_details(self):
        product = Product.objects.create(
            producer=self.producer,
            name='Lettuce',
            category='VEG',
            description='Fresh lettuce',
            price='1.40',
            unit='per head',
            stock_quantity=25,
            is_organic=True
        )

        self.client.login(username='customer_market', password='testpass123')
        response = self.client.get(reverse('customer_market'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)
        self.assertContains(response, self.producer.business_name)
        self.assertContains(response, self.producer.business_address)

    def test_customer_market_redirects_non_customer_user(self):
        self.client.login(username='producer_market', password='testpass123')
        response = self.client.get(reverse('customer_market'))

        self.assertRedirects(response, reverse('home'))


class ProducerBioViewTests(TestCase):
    def setUp(self):
        self.producer_user = User.objects.create_user(username='bio_producer', password='testpass123')
        self.customer_user = User.objects.create_user(username='bio_customer', password='testpass123')

        self.producer = Producer.objects.create(
            user=self.producer_user,
            business_name='Valley Farm',
            contact_name='Val Farmer',
            email='val@example.com',
            business_address='3 Valley Way',
            postcode='BS55EE'
        )
        self.customer = Customer.objects.create(
            user=self.customer_user,
            name='Dana Shopper',
            email='dana@example.com',
            address='8 North Street',
            postcode='BS66FF'
        )

    def test_producer_can_save_bio(self):
        self.client.login(username='bio_producer', password='testpass123')
        response = self.client.post(
            reverse('producer_bio'),
            {'bio': 'We grow seasonal vegetables on our family farm.'}
        )

        self.producer.refresh_from_db()
        self.assertRedirects(response, reverse('producer_bio'))
        self.assertEqual(self.producer.bio, 'We grow seasonal vegetables on our family farm.')

    def test_non_producer_cannot_access_bio_edit_page(self):
        self.client.login(username='bio_customer', password='testpass123')
        response = self.client.get(reverse('producer_bio'))

        self.assertRedirects(response, reverse('home'))

    def test_customer_can_view_producer_public_bio(self):
        self.producer.bio = 'Fresh produce direct from the valley.'
        self.producer.save()

        self.client.login(username='bio_customer', password='testpass123')
        response = self.client.get(reverse('producer_bio_public', args=[self.producer.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.producer.business_name)
        self.assertContains(response, self.producer.bio)


class RecurringOrderFlowTests(TestCase):
    def setUp(self):
        self.customer_user = User.objects.create_user(username='recurring_customer', password='testpass123')
        self.customer = Customer.objects.create(
            user=self.customer_user,
            name='Riley Buyer',
            email='riley@example.com',
            address='11 Weekly Lane',
            postcode='BS77GG'
        )

        self.producer_one_user = User.objects.create_user(username='veg_producer', password='testpass123')
        self.producer_two_user = User.objects.create_user(username='dairy_producer', password='testpass123')
        self.producer_three_user = User.objects.create_user(username='bakery_producer', password='testpass123')

        self.producer_one = Producer.objects.create(
            user=self.producer_one_user,
            business_name='Fresh Fields',
            contact_name='Veg Grower',
            email='veg@example.com',
            business_address='1 Veg Road',
            postcode='BS11AA'
        )
        self.producer_two = Producer.objects.create(
            user=self.producer_two_user,
            business_name='Dairy Farm',
            contact_name='Milk Maker',
            email='dairy@example.com',
            business_address='2 Dairy Road',
            postcode='BS22BB'
        )
        self.producer_three = Producer.objects.create(
            user=self.producer_three_user,
            business_name='Bakery House',
            contact_name='Bread Baker',
            email='bakery@example.com',
            business_address='3 Bakery Road',
            postcode='BS33CC'
        )

        self.veg = Product.objects.create(
            producer=self.producer_one,
            name='Fresh Vegetables',
            category='VEG',
            description='Weekly veg box',
            price='4.50',
            unit='per box',
            stock_quantity=50,
            is_organic=True,
        )
        self.dairy = Product.objects.create(
            producer=self.producer_two,
            name='Dairy Pack',
            category='DAIRY',
            description='Milk and cheese',
            price='5.25',
            unit='per pack',
            stock_quantity=50,
            is_organic=False,
        )
        self.bakery = Product.objects.create(
            producer=self.producer_three,
            name='Bakery Items',
            category='BAKERY',
            description='Bread and rolls',
            price='3.75',
            unit='per bag',
            stock_quantity=50,
            is_organic=False,
        )

    def _next_wednesday(self):
        delivery_date = date.today() + timedelta(days=7)
        while delivery_date.weekday() != 2:
            delivery_date += timedelta(days=1)
        return delivery_date

    def _next_weekday_after(self, anchor_date, weekday):
        days_ahead = (weekday - anchor_date.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return anchor_date + timedelta(days=days_ahead)

    def _create_recurring_checkout_order(self):
        BasketItem.objects.create(customer=self.customer, product=self.veg, quantity=2)
        BasketItem.objects.create(customer=self.customer, product=self.dairy, quantity=1)
        BasketItem.objects.create(customer=self.customer, product=self.bakery, quantity=3)

        self.client.login(username='recurring_customer', password='testpass123')
        delivery_date = self._next_wednesday()

        checkout_response = self.client.post(
            reverse('checkout'),
            {
                'preferred_delivery_date': delivery_date.isoformat(),
                'make_recurring': 'on',
                'recurrence_frequency': 'WEEKLY',
                'recurrence_day': '0',
                'recurring_delivery_day': '0:2',
                'card_holder_name': 'Riley Buyer',
                'card_number': '4242424242424242',
                'card_expiry': '12/30',
                'card_cvv': '123',
            },
        )

        return checkout_response, CustomerOrder.objects.get(customer=self.customer), RecurringOrder.objects.get(customer=self.customer), delivery_date

    def test_recurring_order_flow_supports_next_order_only_modification(self):
        checkout_response, order, recurring_order, delivery_date = self._create_recurring_checkout_order()
        expected_next_run_date = self._next_weekday_after(order.created_at.date(), recurring_order.recurrence_day)

        self.assertRedirects(checkout_response, reverse('order_confirmation', args=[order.id]))
        self.assertEqual(order.items.count(), 3)
        self.assertEqual(recurring_order.frequency, 'WEEKLY')
        self.assertEqual(recurring_order.recurrence_day, 0)
        self.assertEqual(recurring_order.delivery_week_offset, 0)
        self.assertEqual(recurring_order.delivery_day, 2)
        self.assertEqual(recurring_order.next_order_date, expected_next_run_date)
        self.assertEqual(recurring_order.items.get(product=self.veg).quantity, 2)

        manage_response = self.client.get(reverse('manage_recurring_orders'))
        self.assertEqual(manage_response.status_code, 200)
        self.assertContains(manage_response, 'Monday')
        self.assertContains(manage_response, 'Same week - Wednesday')
        self.assertContains(manage_response, expected_next_run_date.strftime('%d %b %Y'))

        update_response = self.client.post(
            reverse('update_recurring_order_next_order', args=[recurring_order.id]),
            {
                f'quantity_{self.veg.id}': '4',
                f'quantity_{self.dairy.id}': '1',
                f'quantity_{self.bakery.id}': '3',
            },
        )

        self.assertRedirects(update_response, reverse('manage_recurring_orders'))
        override = RecurringOrderUpcomingItem.objects.get(
            recurring_order=recurring_order,
            product=self.veg,
            scheduled_for=expected_next_run_date,
        )
        self.assertEqual(override.quantity, 4)
        self.assertEqual(recurring_order.items.get(product=self.veg).quantity, 2)

        manage_response = self.client.get(reverse('manage_recurring_orders'))
        self.assertContains(manage_response, 'Template Qty')
        self.assertContains(manage_response, 'Next Order Qty')
        self.assertContains(manage_response, 'modified')

    def test_recurring_delivery_options_enforce_48_hour_gap(self):
        self.client.login(username='recurring_customer', password='testpass123')
        response = self.client.get(reverse('view_basket'))

        form = response.context['form']
        form.fields['recurrence_day'].initial = 2
        choices = dict(build_delivery_day_choices(2))

        self.assertNotIn('0:3', choices)
        self.assertIn('0:4', choices)
        self.assertIn('0:5', choices)
        self.assertIn('0:6', choices)
        self.assertIn('1:0', choices)

        invalid_form = CheckoutForm(data={
            'preferred_delivery_date': (date.today() + timedelta(days=7)).isoformat(),
            'make_recurring': 'on',
            'recurrence_frequency': 'WEEKLY',
            'recurrence_day': '2',
            'recurring_delivery_day': '0:3',
            'card_holder_name': 'Riley Buyer',
            'card_number': '4242424242424242',
            'card_expiry': '12/30',
            'card_cvv': '123',
        })

        self.assertFalse(invalid_form.is_valid())
        self.assertIn('recurring_delivery_day', invalid_form.errors)

    def test_due_recurring_order_is_generated_and_advanced(self):
        run_date = date.today()
        expected_delivery_date = run_date + timedelta(days=2)
        recurring_order = RecurringOrder.objects.create(
            customer=self.customer,
            frequency='WEEKLY',
            recurrence_day=run_date.weekday(),
            delivery_week_offset=0,
            delivery_day=(run_date.weekday() + 2) % 7,
            delivery_address=self.customer.address,
            next_order_date=run_date,
        )
        RecurringOrderUpcomingItem.objects.create(
            recurring_order=recurring_order,
            product=self.veg,
            scheduled_for=run_date,
            quantity=5,
        )
        recurring_order.items.create(product=self.veg, quantity=2)

        result = process_due_recurring_orders()

        generated_order = CustomerOrder.objects.get(source_recurring_order=recurring_order)
        self.assertEqual(result['created_count'], 1)
        self.assertEqual(generated_order.source_scheduled_for, run_date)
        self.assertEqual(generated_order.preferred_delivery_date, expected_delivery_date)
        self.assertEqual(generated_order.status, 'DELIVERED')
        self.assertEqual(generated_order.items.get(product=self.veg).quantity, 5)

        recurring_order.refresh_from_db()
        self.assertEqual(recurring_order.next_order_date, run_date + timedelta(days=7))
        self.assertFalse(RecurringOrderUpcomingItem.objects.filter(recurring_order=recurring_order, scheduled_for=run_date).exists())
        self.assertTrue(Notification.objects.filter(user=self.customer_user, message__contains='Recurring order').exists())

        self.client.login(username='veg_producer', password='testpass123')
        producer_orders_response = self.client.get(reverse('producer_orders'))
        self.assertContains(producer_orders_response, 'Recurring Orders')
        self.assertContains(producer_orders_response, recurring_order.next_order_date.strftime('%d %b %Y'))

        completed_orders_response = self.client.get(reverse('producer_completed_orders'))
        self.assertContains(completed_orders_response, f'Order #{generated_order.id}')
        self.assertContains(completed_orders_response, recurring_order.get_delivery_schedule_display())


class CommunityBulkOrderTests(TestCase):
    def setUp(self):
        self.customer_user = User.objects.create_user(username='bulk_customer', password='testpass123')
        self.customer = Customer.objects.create(
            user=self.customer_user,
            name='Community Buyer',
            email='bulk@example.com',
            address='12 Community Hall',
            postcode='BS18AA',
        )
        self.producer_user = User.objects.create_user(username='bulk_producer', password='testpass123')
        self.producer = Producer.objects.create(
            user=self.producer_user,
            business_name='Bulk Veg Farm',
            contact_name='Bea Grower',
            email='bea@example.com',
            business_address='4 Field Road',
            postcode='BS29BB',
        )
        self.product = Product.objects.create(
            producer=self.producer,
            name='Community Veg Box',
            category='VEG',
            description='Large seasonal vegetable box',
            price='12.00',
            unit='per box',
            stock_quantity=25,
            is_organic=True,
        )

    def test_customer_can_place_community_group_bulk_order(self):
        BasketItem.objects.create(customer=self.customer, product=self.product, quantity=6)
        self.client.login(username='bulk_customer', password='testpass123')

        response = self.client.post(
            reverse('checkout'),
            {
                'preferred_delivery_date': (date.today() + timedelta(days=3)).isoformat(),
                'is_bulk_order': 'on',
                'group_name': 'Easton Community Kitchen',
                'group_member_count': '18',
                'delivery_instructions': 'Pack into three labelled crates for collection.',
                'card_holder_name': 'Community Buyer',
                'card_number': '4242424242424242',
                'card_expiry': '12/30',
                'card_cvv': '123',
            },
        )

        order = CustomerOrder.objects.get(customer=self.customer)
        self.assertRedirects(response, reverse('order_confirmation', args=[order.id]))
        self.assertTrue(order.is_bulk_order)
        self.assertEqual(order.group_name, 'Easton Community Kitchen')
        self.assertEqual(order.group_member_count, 18)
        self.assertIn('labelled crates', order.delivery_instructions)
        self.assertEqual(order.items.get(product=self.product).quantity, 6)

        confirmation = self.client.get(reverse('order_confirmation', args=[order.id]))
        self.assertContains(confirmation, 'Community Group Order')
        self.assertContains(confirmation, 'Easton Community Kitchen')

    def test_new_customer_order_appears_for_producer_with_alert(self):
        BasketItem.objects.create(customer=self.customer, product=self.product, quantity=2)
        self.client.login(username='bulk_customer', password='testpass123')

        checkout_response = self.client.post(
            reverse('checkout'),
            {
                'preferred_delivery_date': (date.today() + timedelta(days=3)).isoformat(),
                'card_holder_name': 'Community Buyer',
                'card_number': '4242424242424242',
                'card_expiry': '12/30',
                'card_cvv': '123',
            },
        )

        order = CustomerOrder.objects.get(customer=self.customer)
        self.assertRedirects(checkout_response, reverse('order_confirmation', args=[order.id]))
        self.assertTrue(
            Notification.objects.filter(
                user=self.producer_user,
                is_read=False,
                message__contains=f'New order #{order.id}',
            ).exists()
        )

        self.client.logout()
        self.client.login(username='bulk_producer', password='testpass123')

        home_response = self.client.get(reverse('home'))
        self.assertContains(home_response, 'Alerts (1)')

        notifications_response = self.client.get(reverse('notifications'))
        self.assertContains(
            notifications_response,
            f'href="{reverse("producer_orders")}#order-{order.id}"'
        )

        producer_orders_response = self.client.get(reverse('producer_orders'))
        self.assertContains(producer_orders_response, f'Order #{order.id}')
        self.assertContains(producer_orders_response, f'id="order-{order.id}"')
        self.assertContains(producer_orders_response, self.customer.name)
        self.assertContains(producer_orders_response, self.product.name)


class FarmStoryTests(TestCase):
    def setUp(self):
        self.producer_user = User.objects.create_user(username='story_producer', password='testpass123')
        self.customer_user = User.objects.create_user(username='story_customer', password='testpass123')
        self.producer = Producer.objects.create(
            user=self.producer_user,
            business_name='Story Farm',
            contact_name='Sam Story',
            email='story@example.com',
            business_address='9 Orchard Lane',
            postcode='BS31CC',
        )
        self.customer = Customer.objects.create(
            user=self.customer_user,
            name='Story Reader',
            email='reader@example.com',
            address='3 Reading Street',
            postcode='BS42DD',
        )

    def test_producer_can_publish_farm_story_for_customers(self):
        self.client.login(username='story_producer', password='testpass123')
        response = self.client.post(
            reverse('add_farm_story'),
            {
                'title': 'Harvest Week on the Orchard',
                'story': 'We invite customers behind the scenes of our apple harvest.',
                'growing_practices': 'Low spray orchard care and local compost.',
                'published': 'on',
            },
        )

        self.assertRedirects(response, reverse('add_farm_story'))
        story = FarmStory.objects.get(producer=self.producer)
        self.assertEqual(story.title, 'Harvest Week on the Orchard')
        self.assertTrue(story.published)

        self.client.login(username='story_customer', password='testpass123')
        list_response = self.client.get(reverse('farm_story_list'))
        self.assertContains(list_response, 'Harvest Week on the Orchard')
        self.assertContains(list_response, 'Story Farm')

        detail_response = self.client.get(reverse('farm_story_detail', args=[story.id]))
        self.assertContains(detail_response, 'behind the scenes')
        self.assertContains(detail_response, 'Low spray orchard care')

        producer_profile_response = self.client.get(reverse('producer_bio_public', args=[self.producer.id]))
        self.assertContains(producer_profile_response, 'Farm Stories')
        self.assertContains(producer_profile_response, 'Harvest Week on the Orchard')
