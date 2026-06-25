from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinLengthValidator, MinValueValidator
from decimal import Decimal

class Producer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    business_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=254)
    phone_number = PhoneNumberField(null=True, blank=True)
    business_address = models.CharField(max_length=300)
    postcode = models.CharField(max_length=7, validators=[MinLengthValidator(5)])
    bio = models.TextField(blank=True)

    def __str__(self):
        return self.business_name

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    phone_number = PhoneNumberField(null=True, blank=True)
    address = models.CharField(max_length=100)
    postcode = models.CharField(max_length=7, validators=[MinLengthValidator(5)])

    def __str__(self):
        return self.name

class Product(models.Model): 
    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit = models.CharField(max_length=50, help_text="e.g., per kg, per bunch")
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=10)
    is_organic = models.BooleanField(default=False)
    # STRUCTURED ALLERGEN LIST - STORES ZERO OR MORE OF THE UK MAJOR ALLERGEN KEYS
    allergens = models.JSONField(default=list, blank=True)
    is_surplus = models.BooleanField(default=False)
    discount_percent = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    CATEGORY_CHOICES = [
        ('VEG', 'Vegetables'),
        ('FRUIT', 'Fruit'),
        ('MEAT', 'Meat & Poultry'),
        ('DAIRY', 'Dairy'),
        ('BAKERY', 'Bakery'),
    ]

    # SEASON CHOICES USED FOR PRODUCER AVAILABILITY WINDOWS AND CUSTOMER FILTERING
    SEASON_CHOICES = [
        ('SPRING', 'Spring'),
        ('SUMMER', 'Summer'),
        ('AUTUMN', 'Autumn'),
        ('WINTER', 'Winter'),
    ]

    # UK MAJOR ALLERGEN CHOICES USED FOR PRODUCER CHECKBOX INPUTS AND CUSTOMER FILTERING
    ALLERGEN_CHOICES = [
        ('CELERY', 'Celery'),
        ('GLUTEN', 'Cereals containing gluten'),
        ('CRUSTACEANS', 'Crustaceans'),
        ('EGGS', 'Eggs'),
        ('FISH', 'Fish'),
        ('LUPIN', 'Lupin'),
        ('MILK', 'Milk'),
        ('MOLLUSCS', 'Molluscs'),
        ('NUTS', 'Nuts'),
        ('MUSTARD', 'Mustard'),
        ('PEANUTS', 'Peanuts'),
        ('SESAME', 'Sesame'),
        ('SOYBEANS', 'Soybeans'),
        ('SULPHITES', 'Sulphur dioxide and sulphites'),
    ]

    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    seasonal_from = models.CharField(max_length=10, choices=SEASON_CHOICES, default='SPRING')
    seasonal_to = models.CharField(max_length=10, choices=SEASON_CHOICES, default='WINTER')
    image = models.ImageField(upload_to='products/', blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.producer.business_name}"

    def get_allergen_labels(self):
        # MAP STORED ALLERGEN KEYS TO DISPLAY LABELS FOR TEMPLATE OUTPUT
        label_map = dict(self.ALLERGEN_CHOICES)
        return [label_map[key] for key in self.allergens if key in label_map]
    
    @property
    def discounted_price(self):
        if self.is_surplus and self.discount_percent > 0:
            discount_amount = (self.price * Decimal(self.discount_percent)) / Decimal('100')
            return self.price - discount_amount
        return self.price
    
    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.is_surplus and self.discount_percent > 0:
            raise ValidationError("Discounts can only be applied to surplus products.")

# BASKET ITEM MODEL - REPRESENTS A SINGLE PRODUCT SITTING IN A CUSTOMER'S BASKET BEFORE CHECKOUT
class BasketItem(models.Model):
    # LINK TO THE CUSTOMER WHO OWNS THIS BASKET ENTRY
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='basket_items')
    # LINK TO THE PRODUCT BEING HELD IN THE BASKET
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='basket_items')
    # HOW MANY UNITS OF THE PRODUCT THE CUSTOMER WANTS
    quantity = models.PositiveIntegerField(default=1)
    # TIMESTAMP FOR WHEN THE ITEM WAS ADDED
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # PREVENT DUPLICATE ENTRIES - ONE ROW PER CUSTOMER+PRODUCT PAIR
        unique_together = ('customer', 'product')

    def get_subtotal(self):
        # CALCULATE THE LINE TOTAL FOR THIS BASKET ITEM USING SURPLUS-DISCOUNTED PRICE
        return self.product.discounted_price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.product.name} in {self.customer.name}'s basket"


# CUSTOMER ORDER MODEL - REPRESENTS A CONFIRMED ORDER STORED IN THE DATABASE
class CustomerOrder(models.Model):
    # LINK TO THE CUSTOMER WHO PLACED THE ORDER
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    # OPTIONAL LINK BACK TO THE RECURRING TEMPLATE THAT GENERATED THIS ORDER
    source_recurring_order = models.ForeignKey(
        'RecurringOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_orders'
    )
    # THE SCHEDULED RECURRING DATE THIS GENERATED ORDER REPRESENTS
    source_scheduled_for = models.DateField(null=True, blank=True)
    # TIMESTAMP AUTOMATICALLY SET WHEN THE ORDER IS CREATED
    created_at = models.DateTimeField(auto_now_add=True)
    # DELIVERY DETAILS ENTERED BY THE CUSTOMER AT CHECKOUT
    delivery_address = models.CharField(max_length=300)
    preferred_delivery_date = models.DateField()
    # CARD HOLDER NAME FOR REFERENCE
    card_holder_name = models.CharField(max_length=100)
    # ONLY THE LAST 4 DIGITS ARE STORED - FULL CARD NUMBERS ARE NEVER PERSISTED
    card_number_last4 = models.CharField(max_length=4)
    # TOTAL VALUE OF THE ORDER CALCULATED AT CHECKOUT
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    # ORDER STATUS CHOICES
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('READY', 'Ready for Delivery'),
        ('DELIVERED', 'Delivered'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def __str__(self):
        return f"Order #{self.id} by {self.customer.name} on {self.created_at.date()}"


# ORDER ITEM MODEL - REPRESENTS A SINGLE PRODUCT LINE WITHIN A CONFIRMED ORDER
class OrderItem(models.Model):
    # LINK BACK TO THE PARENT ORDER
    order = models.ForeignKey(CustomerOrder, on_delete=models.CASCADE, related_name='items')
    # LINK TO THE PRODUCT THAT WAS ORDERED
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='order_items')
    # QUANTITY ORDERED
    quantity = models.PositiveIntegerField()
    # SNAPSHOT THE PRICE AT TIME OF PURCHASE SO PRICE CHANGES DON'T AFFECT HISTORICAL ORDERS
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def get_subtotal(self):
        # CALCULATE THE SUBTOTAL FOR THIS ORDER LINE
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.product.name} (Order #{self.order.id})"


# RECURRING ORDER MODEL - REPRESENTS A SCHEDULED REPEAT ORDER FOR A CUSTOMER
class RecurringOrder(models.Model):

    WEEKDAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    FREQUENCY_CHOICES = [
        ('WEEKLY', 'Weekly'),
        ('FORTNIGHTLY', 'Fortnightly'),
        ('MONTHLY', 'Monthly'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PAUSED', 'Paused'),
        ('CANCELLED', 'Cancelled'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='recurring_orders')
    frequency = models.CharField(max_length=15, choices=FREQUENCY_CHOICES, default='WEEKLY')
    recurrence_day = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES, default=0)
    delivery_week_offset = models.PositiveSmallIntegerField(default=0)
    delivery_day = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES, default=2)
    delivery_address = models.CharField(max_length=300)
    next_order_date = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.name} - {self.frequency} from {self.next_order_date}"

    def get_delivery_schedule_display(self):
        prefix = 'Same week' if self.delivery_week_offset == 0 else 'Next week'
        return f"{prefix} - {self.get_delivery_day_display()}"


# RECURRING ORDER ITEM MODEL - REPRESENTS A SINGLE PRODUCT IN A RECURRING ORDER TEMPLATE
class RecurringOrderItem(models.Model):
    recurring_order = models.ForeignKey(RecurringOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"


class RecurringOrderUpcomingItem(models.Model):
    recurring_order = models.ForeignKey(RecurringOrder, on_delete=models.CASCADE, related_name='upcoming_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    scheduled_for = models.DateField()
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('recurring_order', 'product', 'scheduled_for')

    def __str__(self):
        return f"Upcoming {self.quantity}x {self.product.name} for recurring order #{self.recurring_order_id}"
    

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.username} - {self.created_at.date()}"


class Recipe(models.Model):

    SEASON_CHOICES = [
        ('SPRING', 'Spring'),
        ('SUMMER', 'Summer'),
        ('AUTUMN', 'Autumn/Winter'),
        ('WINTER', 'Winter'),
        ('ALL', 'Year Round'),
    ]

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name='recipes')
    title = models.CharField(max_length=200)
    description = models.TextField()
    ingredients = models.TextField(help_text="List ingredients, one per line")
    instructions = models.TextField(help_text="Step by step instructions")
    seasonal_tag = models.CharField(max_length=10, choices=SEASON_CHOICES, default='ALL')
    linked_products = models.ManyToManyField(Product, blank=True, related_name='recipes')
    created_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='recipes/', blank=True, null=True)

    def __str__(self):
        return f"{self.title} by {self.producer.business_name}"


class RecipeImage(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='recipes/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for recipe #{self.recipe_id}"

# PRODUCT REVIEW MODEL - ALLOWS CUSTOMERS TO REVIEW ONLY PRODUCTS THEY HAVE PURCHASED
class ProductReview(models.Model):
    # LINK REVIEW TO THE CUSTOMER WHO WROTE IT
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='product_reviews')
    # LINK REVIEW TO THE PRODUCT THAT WAS PURCHASED
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    # LINK REVIEW TO THE EXACT ORDER ITEM PURCHASE (ONE REVIEW PER PURCHASED LINE)
    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name='review')

    # STAR RATING CHOICES
    RATING_CHOICES = [
        (1, '1 - Very Poor'),
        (2, '2 - Poor'),
        (3, '3 - Average'),
        (4, '4 - Good'),
        (5, '5 - Excellent'),
    ]
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)

    # OPTIONAL WRITTEN FEEDBACK
    comment = models.TextField(blank=True)
    is_anonymous = models.BooleanField(default=False)

    # REVIEW TIMESTAMPS
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review by {self.customer.name} for {self.product.name} ({self.rating}/5)"
