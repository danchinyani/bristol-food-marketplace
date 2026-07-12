from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.conf import settings
from decimal import Decimal, InvalidOperation
from django.urls import reverse_lazy
from django.db.models import Q, Sum
from django.contrib.auth.models import User
from .models import Producer, Customer, Product, BasketItem, CustomerOrder, OrderItem, RecurringOrder, RecurringOrderItem, Notification, Recipe, RecipeImage, ProductReview, FarmStory
from .forms import CustomerSignupForm, ProducerSignupForm, ProductForm, ProducerBioForm, CheckoutForm, RecipeForm, ChangeEmailForm, ChangePostcodeForm, FarmStoryForm
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.http import HttpResponse
from datetime import date, timedelta
from .utils import calculate_food_miles
import json
import math
import re
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

try:
    import stripe
except ImportError:
    stripe = None


# ADMIN ROLE CHECK - RETURNS TRUE IF THE USER IS A STAFF OR SUPERUSER
def _is_admin_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _parse_report_date(date_input):
    if not date_input:
        return None
    try:
        return date.fromisoformat(date_input)
    except ValueError:
        return None


def _build_admin_report_data(report_type, parsed_from=None, parsed_to=None):
    # FINANCIAL REPORT DATA
    if report_type == 'financial':
        orders = CustomerOrder.objects.all()

        if parsed_from:
            orders = orders.filter(created_at__date__gte=parsed_from)
        if parsed_to:
            orders = orders.filter(created_at__date__lte=parsed_to)

        total_sales = orders.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        total_commission = round(total_sales * Decimal('0.05'), 2)
        total_producer_payouts = round(total_sales * Decimal('0.95'), 2)
        order_count = orders.count()
        average_order_value = round(total_sales / order_count, 2) if order_count else Decimal('0.00')

        return {
            'type': 'financial',
            'total_sales': total_sales,
            'total_commission': total_commission,
            'total_producer_payouts': total_producer_payouts,
            'order_count': order_count,
            'average_order_value': average_order_value,
        }

    # PLATFORM USAGE REPORT DATA
    if report_type == 'platform_usage':
        users = User.objects.all()
        orders = CustomerOrder.objects.all()
        new_users = users

        if parsed_from:
            new_users = new_users.filter(date_joined__date__gte=parsed_from)
            orders = orders.filter(created_at__date__gte=parsed_from)

        if parsed_to:
            new_users = new_users.filter(date_joined__date__lte=parsed_to)
            orders = orders.filter(created_at__date__lte=parsed_to)

        total_accounts = users.count()
        new_accounts = new_users.count() if (parsed_from or parsed_to) else total_accounts
        total_products = Product.objects.count()
        total_orders = orders.count()

        return {
            'type': 'platform_usage',
            'total_accounts': total_accounts,
            'new_accounts': new_accounts,
            'total_products': total_products,
            'total_orders': total_orders,
        }

    return None


def _expand_season_range(from_season, to_season):
    # EXPAND A CYCLICAL SEASON RANGE (E.G. AUTUMN -> SPRING) INTO ITS INCLUDED SEASONS
    season_order = ['SPRING', 'SUMMER', 'AUTUMN', 'WINTER']
    if from_season not in season_order or to_season not in season_order:
        return set()

    start_index = season_order.index(from_season)
    end_index = season_order.index(to_season)

    included = {from_season}
    current_index = start_index
    while current_index != end_index:
        current_index = (current_index + 1) % len(season_order)
        included.add(season_order[current_index])
    return included


def _season_ranges_overlap(product_from, product_to, filter_from, filter_to):
    # OVERLAP CHECK ENSURES A PRODUCT IS SHOWN IF ANY PART OF ITS WINDOW MATCHES THE FILTER WINDOW
    product_seasons = _expand_season_range(product_from, product_to)
    filter_seasons = _expand_season_range(filter_from, filter_to)
    return bool(product_seasons & filter_seasons)


def _create_customer_order_from_basket(customer_profile, basket_items, form_cleaned_data):
    # CREATE ORDER AND CHILD ORDER ITEMS FROM CURRENT BASKET SNAPSHOT (USES SURPLUS-DISCOUNTED PRICE)
    total = sum(item.product.discounted_price * item.quantity for item in basket_items)

    order = CustomerOrder.objects.create(
        customer=customer_profile,
        delivery_address=customer_profile.address,
        preferred_delivery_date=form_cleaned_data['preferred_delivery_date'],
        card_holder_name=form_cleaned_data.get('card_holder_name') or 'Stripe Checkout',
        card_number_last4=(form_cleaned_data.get('card_number', '')[-4:] or '4242'),
        total_price=total,
        is_bulk_order=form_cleaned_data.get('is_bulk_order', False),
        group_name=form_cleaned_data.get('group_name', ''),
        group_member_count=form_cleaned_data.get('group_member_count'),
        delivery_instructions=form_cleaned_data.get('delivery_instructions', ''),
    )

    for item in basket_items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity,
            unit_price=item.product.discounted_price,
        )

        item.product.stock_quantity -= item.quantity
        item.product.save()

        Notification.objects.create(
            user=item.product.producer.user,
            message=f'New order #{order.id} received for {item.quantity}x {item.product.name} from {order.customer.name}. Delivery: {order.preferred_delivery_date}.'
        )

        if item.product.stock_quantity <= item.product.low_stock_threshold:
            Notification.objects.create(
                user=item.product.producer.user,
                message=f'Low stock alert: {item.product.name} only has {item.product.stock_quantity} units remaining.'
            )

    basket_items.delete()
    return order


def _next_recurring_run_date(anchor_date, recurrence_day):
    days_ahead = (recurrence_day - anchor_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return anchor_date + timedelta(days=days_ahead)


def _create_recurring_order_if_requested(request, customer_profile, order, form_cleaned_data=None):
    # CREATE RECURRING ORDER USING EITHER THE CURRENT CHECKOUT FORM OR LEGACY SESSION DATA
    if form_cleaned_data and form_cleaned_data.get('make_recurring'):
        delivery_slot = form_cleaned_data.get('recurring_delivery_day') or '0:2'
        delivery_week_offset, delivery_day = [int(part) for part in delivery_slot.split(':', 1)]
        recurrence_day = int(form_cleaned_data.get('recurrence_day') or 0)

        recurring_order = RecurringOrder.objects.create(
            customer=customer_profile,
            frequency=form_cleaned_data.get('recurrence_frequency') or 'WEEKLY',
            recurrence_day=recurrence_day,
            delivery_week_offset=delivery_week_offset,
            delivery_day=delivery_day,
            delivery_address=customer_profile.address,
            next_order_date=_next_recurring_run_date(order.created_at.date(), recurrence_day),
        )

        for order_item in order.items.all():
            RecurringOrderItem.objects.create(
                recurring_order=recurring_order,
                product=order_item.product,
                quantity=order_item.quantity,
            )

        messages.success(request, 'Recurring order created successfully!')
        return recurring_order

    if 'recurring_order_data' not in request.session:
        return

    recurring_data = request.session.pop('recurring_order_data')
    recurring_order = RecurringOrder.objects.create(
        customer=customer_profile,
        frequency=recurring_data['frequency'],
        delivery_address=recurring_data['delivery_address'],
        next_order_date=date.fromisoformat(recurring_data['next_order_date']),
    )

    for order_item in order.items.all():
        RecurringOrderItem.objects.create(
            recurring_order=recurring_order,
            product=order_item.product,
            quantity=order_item.quantity,
        )

    messages.success(
        request,
        f'Recurring {recurring_data["frequency"].lower()} order created successfully!'
    )
    return recurring_order


class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'marketplace/change_password.html'
    success_url = reverse_lazy('edit_account')

    def form_valid(self, form):
        messages.success(self.request, 'Your password has been updated successfully.')
        return super().form_valid(form)

POSTCODE_PATTERN = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)


def extract_postcode(text):
    if not text:
        return None
    match = POSTCODE_PATTERN.search(text)
    return match.group(0).upper().replace(" ", "")


@lru_cache(maxsize=128)
def get_postcode_coordinates(postcode):
    if not postcode:
        return None

    url = f"https://api.postcodes.io/postcodes/{quote(postcode)}"

    try:
        with urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError):
        return None

    if payload.get("status") != 200:
        return None

    result = payload.get("result") or {}
    latitude = result.get("latitude")
    longitude = result.get("longitude")

    if latitude is None or longitude is None:
        return None

    return float(latitude), float(longitude)


def distance_in_miles(origin, destination):
    lat1, lon1 = origin
    lat2, lon2 = destination

    radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_food_miles(customer_address, producer_address):
    customer_postcode = extract_postcode(customer_address)
    producer_postcode = extract_postcode(producer_address)

    customer_coordinates = get_postcode_coordinates(customer_postcode)
    producer_coordinates = get_postcode_coordinates(producer_postcode)

    if not customer_coordinates or not producer_coordinates:
        return None

    return round(distance_in_miles(customer_coordinates, producer_coordinates), 1)

def home(request):
    # REDIRECT ADMIN USERS TO THEIR OWN DASHBOARD ON LOGIN
    if _is_admin_user(request.user):
        return redirect('admin_dashboard')

    producer_home_data = None
    customer_home_data = None

    if request.user.is_authenticated:
        producer_profile = _get_logged_in_producer(request.user)
        customer_profile = _get_logged_in_customer(request.user)

        if producer_profile is not None:
            producer_products = Product.objects.filter(producer=producer_profile)
            recent_orders = CustomerOrder.objects.filter(
                items__product__producer=producer_profile
            ).select_related('customer').distinct().order_by('-created_at')[:3]
            recent_reviews = ProductReview.objects.filter(
                product__producer=producer_profile
            ).select_related('customer', 'product').order_by('-created_at')[:3]

            producer_home_data = {
                'product_count': producer_products.count(),
                'low_stock_count': producer_products.filter(stock_quantity__lte=10).count(),
                'pending_orders_count': CustomerOrder.objects.filter(
                    items__product__producer=producer_profile,
                    status='PENDING'
                ).distinct().count(),
                'recent_orders': recent_orders,
                'recent_reviews': recent_reviews,
            }

        if customer_profile is not None:
            customer_orders = CustomerOrder.objects.filter(customer=customer_profile)
            customer_home_data = {
                'market_product_count': Product.objects.count(),
                'basket_lines': BasketItem.objects.filter(customer=customer_profile).count(),
                'active_recurring_count': RecurringOrder.objects.filter(
                    customer=customer_profile,
                    status='ACTIVE'
                ).count(),
                'last_order': customer_orders.order_by('-created_at').first(),
                'recent_orders': customer_orders.order_by('-created_at')[:3],
            }

    return render(
        request,
        'marketplace/home.html',
        {
            'producer_home_data': producer_home_data,
            'customer_home_data': customer_home_data,
        }
    )

def signup_choice(request):
    return render(request, 'marketplace/signup_choice.html')

def signup_producer(request):
    if request.method == 'POST':
        form = ProducerSignupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = ProducerSignupForm()
    return render(request, 'marketplace/signup_producer.html', {'form': form})

def signup_customer(request):
    if request.method == 'POST':
        form = CustomerSignupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home') 
    else:
        form = CustomerSignupForm()
    return render(request, 'marketplace/signup_customer.html', {'form': form})


@login_required
def edit_account(request):
    producer_profile = _get_logged_in_producer(request.user)
    customer_profile = _get_logged_in_customer(request.user)
    profile = producer_profile or customer_profile

    if profile is None:
        messages.error(request, 'No editable profile was found for your account.')
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'change_email':
            email_form = ChangeEmailForm(request.POST)
            postcode_form = ChangePostcodeForm(initial={'postcode': profile.postcode})

            if email_form.is_valid():
                new_email = email_form.cleaned_data['email']
                profile.email = new_email
                profile.save(update_fields=['email'])
                request.user.email = new_email
                request.user.save(update_fields=['email'])
                messages.success(request, 'Email updated successfully.')
                return redirect('edit_account')

        elif action == 'change_postcode':
            postcode_form = ChangePostcodeForm(request.POST)
            email_form = ChangeEmailForm(initial={'email': profile.email})

            if postcode_form.is_valid():
                profile.postcode = postcode_form.cleaned_data['postcode']
                profile.save(update_fields=['postcode'])
                messages.success(request, 'Postcode updated successfully.')
                return redirect('edit_account')

        else:
            email_form = ChangeEmailForm(initial={'email': profile.email})
            postcode_form = ChangePostcodeForm(initial={'postcode': profile.postcode})
    else:
        email_form = ChangeEmailForm(initial={'email': profile.email})
        postcode_form = ChangePostcodeForm(initial={'postcode': profile.postcode})

    return render(
        request,
        'marketplace/edit_account.html',
        {
            'profile': profile,
            'is_producer': producer_profile is not None,
            'is_customer': customer_profile is not None,
            'email_form': email_form,
            'postcode_form': postcode_form,
        },
    )

@login_required
def add_product(request):
    try:
        producer_profile = request.user.producer
    except Producer.DoesNotExist:
        return redirect('home')

    producer_products = producer_profile.products.order_by('name')

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.producer = producer_profile
            product.save()
            return redirect('add_product')
    else:
        form = ProductForm()
    
    return render(
        request,
        'marketplace/producer_add_product.html',
        {
            'form': form,
            'producer_products': producer_products,
        }
    )


def _get_logged_in_producer(user):
    try:
        return user.producer
    except Producer.DoesNotExist:
        return None


def _get_logged_in_customer(user):
    try:
        return user.customer
    except Customer.DoesNotExist:
        return None



# ADMIN DASHBOARD VIEW

@login_required
def admin_dashboard(request):
    # ONLY ALLOW STAFF / SUPERUSERS TO ACCESS THE ADMIN DASHBOARD
    if not _is_admin_user(request.user):
        return redirect('home')

    return render(
        request,
        'marketplace/admin_dashboard.html',
        {
            'total_orders': CustomerOrder.objects.count(),
            'total_producers': Producer.objects.count(),
            'total_customers': Customer.objects.count(),
        }
    )



#DISPLAYS ALL PRODUCER AND CUSTOMER PROFILES

@login_required
def admin_profiles(request):
    if not _is_admin_user(request.user):
        return redirect('home')

    producers = Producer.objects.select_related('user').order_by('business_name')
    customers = Customer.objects.select_related('user').order_by('name')

    return render(
        request,
        'marketplace/admin_profiles.html',
        {
            'producers': producers,
            'customers': customers,
            'total_producers': producers.count(),
            'total_customers': customers.count(),
        }
    )



# DISPLAYS ALL ORDERS ACROSS THE PLATFORM

@login_required
def admin_orders(request):
    if not _is_admin_user(request.user):
        return redirect('home')

    orders = CustomerOrder.objects.select_related(
        'customer__user'
    ).prefetch_related(
        'items__product__producer'
    ).order_by('-created_at')

    return render(
        request,
        'marketplace/admin_orders.html',
        {
            'orders': orders,
            'total_orders': orders.count(),
        }
    )



# GENERATES FINANCIAL OR PLATFORM USAGE REPORTS

@login_required
def admin_reports(request):
    if not _is_admin_user(request.user):
        return redirect('home')

    report_type = request.GET.get('report_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    parsed_from = _parse_report_date(date_from)
    parsed_to = _parse_report_date(date_to)
    report_data = _build_admin_report_data(report_type, parsed_from, parsed_to)

    return render(
        request,
        'marketplace/admin_reports.html',
        {
            'report_type': report_type,
            'date_from': date_from,
            'date_to': date_to,
            'report_data': report_data,
        }
    )


@login_required
def producer_product_actions(request, product_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    product = get_object_or_404(Product, id=product_id, producer=producer_profile)
    return render(
        request,
        'marketplace/producer_product_actions.html',
        {'product': product}
    )


@login_required
def edit_product(request, product_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    product = get_object_or_404(Product, id=product_id, producer=producer_profile)

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            return redirect('add_product')
    else:
        form = ProductForm(instance=product)

    return render(
        request,
        'marketplace/producer_edit_product.html',
        {
            'form': form,
            'product': product,
        }
    )


@login_required
def delete_product(request, product_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    product = get_object_or_404(Product, id=product_id, producer=producer_profile)

    if request.method == 'POST':
        product.delete()

    return redirect('add_product')


@login_required
def customer_market(request):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # MARKET FILTER INPUTS FROM QUERY STRING
    search_input = request.GET.get('search', '').strip()
    min_price_input = request.GET.get('min_price', '').strip()
    max_price_input = request.GET.get('max_price', '').strip()
    organic_input = request.GET.get('organic', 'all').strip().lower()
    category_input = request.GET.get('category', '').strip()
    allergen_inputs = request.GET.getlist('allergens')
    season_from_input = request.GET.get('season_from', '').strip().upper()
    season_to_input = request.GET.get('season_to', '').strip().upper()

    products = Product.objects.select_related('producer').order_by('name')

    # APPLY CASE-INSENSITIVE NAME SEARCH WHEN A SEARCH TERM IS PROVIDED
    if search_input:
        products = products.filter(name__icontains=search_input)

    # APPLY MIN/MAX PRICE FILTERS WHEN VALUES ARE VALID DECIMALS
    if min_price_input:
        try:
            min_price = Decimal(min_price_input)
            products = products.filter(price__gte=min_price)
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid minimum price filter value.')

    if max_price_input:
        try:
            max_price = Decimal(max_price_input)
            products = products.filter(price__lte=max_price)
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid maximum price filter value.')

    # APPLY ORGANIC STATUS FILTER
    if organic_input == 'true':
        products = products.filter(is_organic=True)
    elif organic_input == 'false':
        products = products.filter(is_organic=False)

    # APPLY CATEGORY FILTER ONLY WHEN IT MATCHES A VALID CATEGORY KEY
    valid_categories = {choice[0] for choice in Product.CATEGORY_CHOICES}
    if category_input in valid_categories:
        products = products.filter(category=category_input)

    # APPLY ALLERGEN FILTER IN REVERSE - REMOVE PRODUCTS CONTAINING ANY SELECTED ALLERGEN
    valid_allergens = {choice[0] for choice in Product.ALLERGEN_CHOICES}
    selected_allergens = [allergen for allergen in allergen_inputs if allergen in valid_allergens]
    if selected_allergens:
        allergen_query = Q()
        for allergen in selected_allergens:
            allergen_query |= Q(allergens__contains=[allergen])
        products = products.exclude(allergen_query)

    # APPLY SEASON AVAILABILITY FILTER USING THE SAME FROM/TO MODEL AS PRODUCERS
    valid_seasons = [choice[0] for choice in Product.SEASON_CHOICES]
    if season_from_input and season_to_input and season_from_input in valid_seasons and season_to_input in valid_seasons:
        products = [
            product for product in products
            if _season_ranges_overlap(
                product.seasonal_from,
                product.seasonal_to,
                season_from_input,
                season_to_input
            )
        ]

    products_with_miles = []
    miles_cache = {}

    for product in products:
        producer_postcode = product.producer.postcode
        cache_key = (customer_profile.postcode, producer_postcode)

        if cache_key not in miles_cache:
            miles_cache[cache_key] = calculate_food_miles(
                customer_profile.postcode,
                producer_postcode
            )

        products_with_miles.append({
            'product': product,
            'food_miles': miles_cache[cache_key],
        })

    return render(
        request,
        'marketplace/customer_market.html',
        {
            'products': products,
            'products_with_miles': products_with_miles,
            'category_choices': Product.CATEGORY_CHOICES,
            'allergen_choices': Product.ALLERGEN_CHOICES,
            'season_choices': Product.SEASON_CHOICES,
            'selected_filters': {
                'search': search_input,
                'min_price': min_price_input,
                'max_price': max_price_input,
                'organic': organic_input,
                'category': category_input,
                'allergens': selected_allergens,
                'season_from': season_from_input,
                'season_to': season_to_input,
            },
        }
    )


@login_required
def producer_bio(request):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    if request.method == 'POST':
        form = ProducerBioForm(request.POST, instance=producer_profile)
        if form.is_valid():
            form.save()
            return redirect('producer_bio')
    else:
        form = ProducerBioForm(instance=producer_profile)

    return render(
        request,
        'marketplace/producer_bio.html',
        {
            'form': form,
            'producer': producer_profile,
        }
    )


@login_required
def producer_bio_public(request, producer_id):
    producer = get_object_or_404(Producer, id=producer_id)
    farm_stories = producer.farm_stories.filter(published=True)
    return render(
        request,
        'marketplace/producer_bio_public.html',
        {
            'producer': producer,
            'farm_stories': farm_stories,
        }
    )


# ADD TO BASKET VIEW 
@login_required
def add_to_basket(request, product_id):
    # VERIFY THE LOGGED-IN USER IS A CUSTOMER
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # FETCH THE PRODUCT OR RETURN 404 IF IT DOES NOT EXIST
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        # READ THE REQUESTED QUANTITY FROM THE FORM, DEFAULTING TO 1
        try:
            quantity = int(request.POST.get('quantity', 1))
        except ValueError:
            quantity = 1

        # REJECT QUANTITIES OF ZERO OR LESS
        if quantity < 1:
            messages.error(request, 'Quantity must be at least 1.')
            return redirect('customer_market')

        # GET THE EXISTING BASKET ITEM IF PRESENT, OR PREPARE A NEW ONE
        basket_item, created = BasketItem.objects.get_or_create(
            customer=customer_profile,
            product=product,
            defaults={'quantity': 0},
        )

        # CALCULATE THE NEW TOTAL QUANTITY AFTER ADDING THE REQUESTED AMOUNT
        new_quantity = basket_item.quantity + quantity

        # PREVENT ADDING MORE ITEMS THAN ARE CURRENTLY IN STOCK
        if new_quantity > product.stock_quantity:
            available = product.stock_quantity - basket_item.quantity
            if available <= 0:
                messages.error(request, f'No more stock available for "{product.name}".')
            else:
                messages.error(
                    request,
                    f'Only {available} more unit(s) of "{product.name}" available.'
                )
            return redirect('customer_market')

        # SAVE THE UPDATED QUANTITY TO THE DATABASE
        basket_item.quantity = new_quantity
        basket_item.save()
        messages.success(request, f'Added {quantity}x "{product.name}" to your basket.')

    return redirect('customer_market')

def _build_basket_food_miles_context(customer_profile, basket_items):
    basket_with_miles = []
    total_food_miles = 0
    miles_cache = {}

    for item in basket_items:
        producer_postcode = (item.product.producer.postcode or "").strip()
        customer_postcode = (customer_profile.postcode or "").strip()
        cache_key = (customer_postcode, producer_postcode)

        if cache_key not in miles_cache:
            miles_cache[cache_key] = calculate_food_miles(
                customer_postcode,
                producer_postcode
            )

        food_miles = miles_cache[cache_key]

        basket_with_miles.append({
            'item': item,
            'food_miles': food_miles,
        })

        if food_miles is not None:
            total_food_miles += food_miles

    return basket_with_miles, round(total_food_miles, 1)


# VIEW BASKET VIEW - DISPLAYS ALL ITEMS IN THE CUSTOMER'S BASKET AND THE CHECKOUT FORM
@login_required
def view_basket(request):
    # VERIFY THE LOGGED-IN USER IS A CUSTOMER
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # FETCH ALL BASKET ITEMS FOR THIS CUSTOMER WITH THEIR RELATED PRODUCT DATA
    basket_items = BasketItem.objects.filter(customer=customer_profile).select_related('product__producer')

    # CALCULATE THE GRAND TOTAL ACROSS ALL BASKET ITEMS
    total = sum(item.get_subtotal() for item in basket_items)
    basket_with_miles, total_food_miles = _build_basket_food_miles_context(
    customer_profile,
    basket_items
)

    # CHECK IF A RECURRING ORDER SETUP IS IN PROGRESS
    recurring_order_setup = request.session.get('recurring_order_data', None)

    # PRE-FILL THE PREFERRED DELIVERY DATE FROM THE RECURRING ORDER DATE IF ONE IS IN PROGRESS
    # OR FROM A QUERY PARAM PASSED AFTER CANCELLING A RECURRING ORDER VIA THE UPDATE DATE BUTTON
    form_initial = {}
    preferred_date_param = request.GET.get('preferred_delivery_date', '').strip()
    if preferred_date_param:
        form_initial['preferred_delivery_date'] = preferred_date_param
    elif recurring_order_setup and recurring_order_setup.get('next_order_date'):
        form_initial['preferred_delivery_date'] = recurring_order_setup['next_order_date']
    form = CheckoutForm(initial=form_initial)

    return render(
        request,
        'marketplace/basket.html',
        {
            'basket_items': basket_items,
            'total': total,
            'form': form,
            'recurring_order_setup': recurring_order_setup,
            'customer_address': customer_profile.address,
            'basket_with_miles': basket_with_miles,
            'total_food_miles': total_food_miles,
        }
    )


# REMOVE FROM BASKET VIEW - DELETES A SINGLE ITEM FROM THE CUSTOMER'S BASKET
@login_required
def remove_from_basket(request, item_id):
    # VERIFY THE LOGGED-IN USER IS A CUSTOMER
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # FETCH THE BASKET ITEM, ENSURING IT BELONGS TO THIS CUSTOMER
    basket_item = get_object_or_404(BasketItem, id=item_id, customer=customer_profile)

    if request.method == 'POST':
        # DELETE THE ITEM FROM THE BASKET
        basket_item.delete()
        messages.success(request, f'Removed "{basket_item.product.name}" from your basket.')

    return redirect('view_basket')


# CHECKOUT VIEW - PROCESSES THE CHECKOUT FORM AND CREATES A CONFIRMED ORDER
@login_required
def checkout(request):
    # VERIFY THE LOGGED-IN USER IS A CUSTOMER
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # FETCH ALL CURRENT BASKET ITEMS FOR THIS CUSTOMER
    basket_items = BasketItem.objects.filter(customer=customer_profile).select_related('product')

    # REDIRECT BACK TO BASKET IF IT IS EMPTY
    if not basket_items.exists():
        messages.error(request, 'Your basket is empty.')
        return redirect('view_basket')

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            # IF A RECURRING ORDER IS PENDING AND THE DELIVERY DATE HAS BEEN CHANGED, CANCEL IT
            recurring_order_data = request.session.get('recurring_order_data')
            if recurring_order_data:
                submitted_date = form.cleaned_data['preferred_delivery_date'].isoformat()
                if submitted_date != recurring_order_data.get('next_order_date'):
                    del request.session['recurring_order_data']
                    messages.warning(
                        request,
                        'Recurring order cancelled due to updated delivery date.'
                    )

            # RE-CHECK STOCK AVAILABILITY FOR ALL ITEMS BEFORE CONFIRMING THE ORDER
            for item in basket_items:
                if item.quantity > item.product.stock_quantity:
                    messages.error(
                        request,
                        f'Sorry, "{item.product.name}" now only has {item.product.stock_quantity} unit(s) in stock. '
                        f'Please update your basket.'
                    )
                    return redirect('view_basket')

            total = sum(item.product.discounted_price * item.quantity for item in basket_items)

            stripe_secret_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
            stripe_publishable_key = getattr(settings, 'STRIPE_PUBLISHABLE_KEY', '')
            use_stripe_checkout = bool(stripe and stripe_secret_key and stripe_publishable_key)

            if use_stripe_checkout:
                # CREATE STRIPE TEST SESSION AND FINALIZE ORDER ONLY AFTER SUCCESS CALLBACK
                stripe.api_key = stripe_secret_key
                try:
                    checkout_session = stripe.checkout.Session.create(
                        mode='payment',
                        payment_method_types=['card'],
                        line_items=[
                            {
                                'price_data': {
                                    'currency': 'gbp',
                                    'product_data': {
                                        'name': 'BRFN Basket Order',
                                    },
                                    'unit_amount': int(total * 100),
                                },
                                'quantity': 1,
                            }
                        ],
                        success_url=request.build_absolute_uri('/orders/checkout/stripe/success/') + '?session_id={CHECKOUT_SESSION_ID}',
                        cancel_url=request.build_absolute_uri('/basket/'),
                    )
                except Exception:
                    messages.error(request, 'Stripe checkout could not be started. Please try again.')
                    return redirect('view_basket')

                request.session['pending_checkout_data'] = {
                    'preferred_delivery_date': form.cleaned_data['preferred_delivery_date'].isoformat(),
                    'card_holder_name': form.cleaned_data['card_holder_name'],
                    'card_number_last4': form.cleaned_data['card_number'][-4:],
                    'customer_id': customer_profile.id,
                }
                return redirect(checkout_session.url)

            # NON-STRIPE FALLBACK: COMPLETE ORDER IMMEDIATELY USING CURRENT FLOW
            order = _create_customer_order_from_basket(customer_profile, basket_items, form.cleaned_data)
            _create_recurring_order_if_requested(request, customer_profile, order, form.cleaned_data)
            return redirect('order_confirmation', order_id=order.id)

        else:
            # FORM IS INVALID - RE-RENDER THE BASKET PAGE WITH ERRORS
                        basket_items_list = BasketItem.objects.filter(
                            customer=customer_profile
                        ).select_related('product__producer')

                        total = sum(item.get_subtotal() for item in basket_items_list)

                        basket_with_miles, total_food_miles = _build_basket_food_miles_context(
                        customer_profile,
                        basket_items_list
                        )

                        return render(
                request,
                'marketplace/basket.html',
                {
                    'basket_items': basket_items_list,
                    'basket_with_miles': basket_with_miles,
                    'total_food_miles': total_food_miles,
                    'total': total,
                    'form': form,
                    'recurring_order_setup': request.session.get('recurring_order_data', None),
                    'customer_address': customer_profile.address,
                }
            )
    return redirect('view_basket')


@login_required
def stripe_checkout_success(request):
    # FINALIZE ORDER ONLY IF STRIPE SESSION IS PRESENT AND PAID
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    session_id = request.GET.get('session_id', '')
    pending_data = request.session.get('pending_checkout_data')
    if not session_id or not pending_data:
        messages.error(request, 'Checkout session not found. Please try again.')
        return redirect('view_basket')

    if pending_data.get('customer_id') != customer_profile.id:
        messages.error(request, 'Checkout session does not belong to this customer.')
        return redirect('view_basket')

    stripe_secret_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    if not stripe or not stripe_secret_key:
        messages.error(request, 'Stripe is not configured in this environment.')
        return redirect('view_basket')

    stripe.api_key = stripe_secret_key
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        messages.error(request, 'Could not verify Stripe checkout session.')
        return redirect('view_basket')

    if checkout_session.payment_status != 'paid':
        messages.error(request, 'Payment was not completed. Please try again.')
        return redirect('view_basket')

    basket_items = BasketItem.objects.filter(customer=customer_profile).select_related('product')
    if not basket_items.exists():
        messages.error(request, 'Your basket is empty. Nothing to confirm.')
        return redirect('view_basket')

    for item in basket_items:
        if item.quantity > item.product.stock_quantity:
            messages.error(
                request,
                f'Sorry, "{item.product.name}" now only has {item.product.stock_quantity} unit(s) in stock. Please update your basket.'
            )
            return redirect('view_basket')

    order_data = {
        'delivery_address': customer_profile.address,
        'preferred_delivery_date': date.fromisoformat(pending_data['preferred_delivery_date']),
        'card_holder_name': pending_data.get('card_holder_name') or 'Stripe Checkout',
        'card_number': pending_data.get('card_number_last4') or '4242',
    }

    order = _create_customer_order_from_basket(customer_profile, basket_items, order_data)
    _create_recurring_order_if_requested(request, customer_profile, order)

    request.session.pop('pending_checkout_data', None)
    return redirect('order_confirmation', order_id=order.id)


# ORDER CONFIRMATION VIEW - DISPLAYS A SUMMARY OF THE COMPLETED ORDER
@login_required
def order_confirmation(request, order_id):
    # VERIFY THE LOGGED-IN USER IS A CUSTOMER
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # FETCH THE ORDER, ENSURING IT BELONGS TO THIS CUSTOMER
    order = get_object_or_404(CustomerOrder, id=order_id, customer=customer_profile)

    # FETCH ALL ITEMS ASSOCIATED WITH THIS ORDER
    order_items = order.items.select_related('product').all()

    return render(
        request,
        'marketplace/order_confirmation.html',
        {
            'order': order,
            'order_items': order_items,
        }
    )


# ORDER HISTORY VIEW - DISPLAYS ALL PAST ORDERS FOR THE CUSTOMER
@login_required
def order_history(request):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    orders = CustomerOrder.objects.filter(
        customer=customer_profile
    ).prefetch_related('items__product__producer').order_by('-created_at')

    # ATTACH REVIEW OBJECTS TO EACH ORDER ITEM FOR TEMPLATE RENDERING
    order_item_ids = [item.id for order in orders for item in order.items.all()]
    reviews_by_order_item_id = {
        review.order_item_id: review
        for review in ProductReview.objects.filter(order_item_id__in=order_item_ids)
    }

    for order in orders:
        for item in order.items.all():
            item.customer_review = reviews_by_order_item_id.get(item.id)

    return render(
        request,
        'marketplace/order_history.html',
        {'orders': orders}
    )


# SUBMIT PRODUCT REVIEW VIEW - ALLOWS REVIEW ONLY FOR PRODUCTS THE CUSTOMER HAS PURCHASED
@login_required
def submit_product_review(request, order_item_id):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # ENSURE THE TARGET ORDER ITEM BELONGS TO THE LOGGED-IN CUSTOMER'S ORDER HISTORY
    order_item = get_object_or_404(
        OrderItem.objects.select_related('order', 'product'),
        id=order_item_id,
        order__customer=customer_profile,
    )

    # ONLY ALLOW REVIEWS AFTER THE PRODUCER HAS MARKED THE ORDER AS DELIVERED
    if order_item.order.status != 'DELIVERED':
        messages.error(request, 'You can only review products after your order has been delivered.')
        return redirect('order_history')

    if request.method == 'POST':
        # READ AND VALIDATE RATING INPUT
        rating_raw = request.POST.get('rating', '').strip()
        comment = request.POST.get('comment', '').strip()
        is_anonymous = request.POST.get('is_anonymous') == 'on'

        try:
            rating = int(rating_raw)
        except (TypeError, ValueError):
            rating = None

        if rating not in {1, 2, 3, 4, 5}:
            messages.error(request, 'Please select a valid rating between 1 and 5.')
            return redirect('order_history')

        # CREATE OR UPDATE A REVIEW FOR THIS PURCHASED ORDER ITEM
        review, created = ProductReview.objects.get_or_create(
            order_item=order_item,
            defaults={
                'customer': customer_profile,
                'product': order_item.product,
                'rating': rating,
                'comment': comment,
                'is_anonymous': is_anonymous,
            },
        )

        if review.customer_id != customer_profile.id:
            messages.error(request, 'You are not allowed to update this review.')
            return redirect('order_history')

        # SAVE UPDATED REVIEW VALUES
        review.product = order_item.product
        review.rating = rating
        review.comment = comment
        review.is_anonymous = is_anonymous
        review.save()

        # CREATE A PRODUCER NOTIFICATION SO REVIEWS APPEAR IN THE NOTIFICATIONS PAGE
        if created:
            notification_message = (
                f'Review received: {customer_profile.name} rated "{order_item.product.name}" '
                f'{rating}/5 on order #{order_item.order.id}.'
            )
        else:
            notification_message = (
                f'Review updated: {customer_profile.name} changed review for "{order_item.product.name}" '
                f'to {rating}/5 on order #{order_item.order.id}.'
            )

        Notification.objects.create(
            user=order_item.product.producer.user,
            message=notification_message,
        )

        messages.success(request, f'Review saved for "{order_item.product.name}".')

    return redirect('order_history')


# PRODUCER REVIEWS VIEW - SHOWS ALL REVIEWS LEFT BY CUSTOMERS FOR THIS PRODUCER'S PRODUCTS
@login_required
def producer_reviews(request):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    # FETCH ALL REVIEWS FOR PRODUCTS OWNED BY THIS PRODUCER
    reviews = ProductReview.objects.filter(
        product__producer=producer_profile
    ).select_related(
        'customer__user',
        'product',
        'order_item__order'
    ).order_by('-created_at')

    return render(
        request,
        'marketplace/producer_reviews.html',
        {'reviews': reviews}
    )


# REORDER VIEW - ADDS ALL ITEMS FROM A PREVIOUS ORDER BACK INTO THE BASKET
@login_required
def reorder(request, order_id):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    order = get_object_or_404(CustomerOrder, id=order_id, customer=customer_profile)

    unavailable = []
    for item in order.items.select_related('product'):
        product = item.product
        if product.stock_quantity >= item.quantity:
            basket_item, created = BasketItem.objects.get_or_create(
                customer=customer_profile,
                product=product,
                defaults={'quantity': 0}
            )
            basket_item.quantity += item.quantity
            basket_item.save()
        else:
            unavailable.append(product.name)

    if unavailable:
        messages.warning(
            request,
            f'Some items were unavailable and skipped: {", ".join(unavailable)}'
        )
    else:
        messages.success(request, 'All items added to your basket.')

    return redirect('view_basket')


# DOWNLOAD RECEIPT VIEW - GENERATES A PDF RECEIPT FOR A SPECIFIC ORDER
@login_required
def download_receipt(request, order_id):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    order = get_object_or_404(CustomerOrder, id=order_id, customer=customer_profile)
    order_items = order.items.select_related('product').all()

    # CREATE PDF RESPONSE
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_order_{order.id}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    y = height - 50

    # HEADER
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, y, "Bristol Regional Food Network")
    y -= 25
    p.setFont("Helvetica", 12)
    p.drawString(50, y, "Order Receipt")
    y -= 30

    # ORDER DETAILS
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, f"Order #: {order.id}")
    y -= 18
    p.setFont("Helvetica", 11)
    p.drawString(50, y, f"Date Placed: {order.created_at.strftime('%d %B %Y')}")
    y -= 18
    p.drawString(50, y, f"Delivery Date: {order.preferred_delivery_date.strftime('%d %B %Y')}")
    y -= 18
    p.drawString(50, y, f"Delivery Address: {order.delivery_address}")
    y -= 18
    p.drawString(50, y, f"Status: {order.get_status_display()}")
    y -= 18
    p.drawString(50, y, f"Card: **** **** **** {order.card_number_last4}")
    y -= 30

    # ITEMS TABLE HEADER
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, "Product")
    p.drawString(250, y, "Producer")
    p.drawString(400, y, "Qty")
    p.drawString(450, y, "Unit Price")
    p.drawString(530, y, "Subtotal")
    y -= 5
    p.line(50, y, 580, y)
    y -= 18

    # ITEMS
    p.setFont("Helvetica", 10)
    for item in order_items:
        p.drawString(50, y, item.product.name[:25])
        p.drawString(250, y, item.product.producer.business_name[:20])
        p.drawString(400, y, str(item.quantity))
        p.drawString(450, y, f"£{item.unit_price}")
        p.drawString(530, y, f"£{item.get_subtotal()}")
        y -= 18

    # TOTAL
    y -= 10
    p.line(50, y, 580, y)
    y -= 20
    p.setFont("Helvetica-Bold", 12)
    p.drawString(450, y, f"Total: £{order.total_price}")

    p.showPage()
    p.save()
    return response


def _group_order_items_by_order(order_items):
    orders_dict = {}
    for item in order_items:
        order = item.order
        if order.id not in orders_dict:
            orders_dict[order.id] = {
                'order': order,
                'recurring_order': order.source_recurring_order,
                'items': []
            }
        orders_dict[order.id]['items'].append(item)
    return list(orders_dict.values())


def _build_producer_recurring_entries(producer_profile):
    recurring_orders = RecurringOrder.objects.filter(
        status='ACTIVE',
        items__product__producer=producer_profile,
    ).select_related(
        'customer'
    ).prefetch_related(
        'items__product',
        'upcoming_items'
    ).distinct().order_by('next_order_date')

    entries = []
    for recurring_order in recurring_orders:
        overrides = {
            item.product_id: item.quantity
            for item in recurring_order.upcoming_items.filter(
                scheduled_for=recurring_order.next_order_date
            )
        }
        items = []
        for item in recurring_order.items.select_related('product').filter(
            product__producer=producer_profile
        ):
            items.append({
                'product': item.product,
                'template_quantity': item.quantity,
                'quantity': overrides.get(item.product_id, item.quantity),
            })

        if items:
            entries.append({
                'recurring_order': recurring_order,
                'items': items,
            })

    return entries


# PRODUCER ORDERS VIEW - DISPLAYS ALL INCOMING ORDERS FOR THE PRODUCER
@login_required
def producer_orders(request):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    one_off_items = OrderItem.objects.filter(
        product__producer=producer_profile,
        order__source_recurring_order__isnull=True,
    ).exclude(
        order__status='DELIVERED'
    ).select_related(
        'order__customer', 'order__source_recurring_order', 'product'
    ).order_by('order__preferred_delivery_date')

    one_off_orders = _group_order_items_by_order(one_off_items)
    recurring_orders = _build_producer_recurring_entries(producer_profile)

    return render(
        request,
        'marketplace/producer_orders.html',
        {
            'one_off_orders': one_off_orders,
            'recurring_orders': recurring_orders,
        }
    )


# PRODUCER COMPLETED ORDERS VIEW - SHOWS DELIVERED ORDERS FOR THE PRODUCER
@login_required
def producer_completed_orders(request):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    one_off_items = OrderItem.objects.filter(
        product__producer=producer_profile,
        order__status='DELIVERED',
        order__source_recurring_order__isnull=True,
    ).select_related(
        'order__customer', 'order__source_recurring_order', 'product'
    ).order_by('-order__preferred_delivery_date')

    recurring_items = OrderItem.objects.filter(
        product__producer=producer_profile,
        order__status='DELIVERED',
        order__source_recurring_order__isnull=False,
    ).select_related(
        'order__customer', 'order__source_recurring_order', 'product'
    ).order_by('-order__preferred_delivery_date')

    one_off_orders = _group_order_items_by_order(one_off_items)
    recurring_orders = _group_order_items_by_order(recurring_items)

    return render(
        request,
        'marketplace/producer_completed_orders.html',
        {
            'one_off_orders': one_off_orders,
            'recurring_orders': recurring_orders,
        }
    )


# UPDATE ORDER STATUS VIEW - ALLOWS PRODUCERS TO UPDATE THE STATUS OF AN ORDER
@login_required
def update_order_status(request, order_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    order = get_object_or_404(CustomerOrder, id=order_id)
    is_producers_order = order.items.filter(
        product__producer=producer_profile
    ).exists()

    if not is_producers_order:
        return redirect('producer_orders')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = [choice[0] for choice in CustomerOrder.STATUS_CHOICES]
        if new_status in valid_statuses:
            order.status = new_status
            order.save()

            # NOTIFY THE CUSTOMER OF THE STATUS CHANGE
            Notification.objects.create(
                user=order.customer.user,
                message=f'Your order #{order.id} from {producer_profile.business_name} is now {order.get_status_display()}.'
            )

            messages.success(request, f'Order #{order.id} status updated to {order.get_status_display()}.')

    return redirect('producer_orders')


# PAYMENT SETTLEMENTS VIEW - DISPLAYS WEEKLY PAYMENT SUMMARIES FOR THE PRODUCER
@login_required
def payment_settlements(request):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    # GET ALL DELIVERED ORDERS FOR THIS PRODUCER
    order_items = OrderItem.objects.filter(
        product__producer=producer_profile,
        order__status='DELIVERED'
    ).select_related('order', 'product').order_by('-order__created_at')

    # GROUP BY WEEK
    weeks = {}
    for item in order_items:
        order_date = item.order.created_at.date()
        week_start = order_date - timedelta(days=order_date.weekday())
        week_end = week_start + timedelta(days=6)
        week_key = week_start

        if week_key not in weeks:
            weeks[week_key] = {
                'week_start': week_start,
                'week_end': week_end,
                'items': [],
                'gross_total': 0,
                'commission': 0,
                'producer_payment': 0,
            }

        subtotal = item.get_subtotal()
        commission = round(subtotal * Decimal('0.05'), 2)
        producer_payment = round(subtotal * Decimal('0.95'), 2)

        weeks[week_key]['items'].append({
            'item': item,
            'subtotal': subtotal,
            'commission': commission,
            'producer_payment': producer_payment,
        })
        weeks[week_key]['gross_total'] += subtotal
        weeks[week_key]['commission'] += commission
        weeks[week_key]['producer_payment'] += producer_payment

    # SORT WEEKS MOST RECENT FIRST
    sorted_weeks = sorted(weeks.values(), key=lambda w: w['week_start'], reverse=True)

    # CALCULATE YEAR TO DATE TOTALS
    ytd_gross = sum(w['gross_total'] for w in sorted_weeks)
    ytd_commission = sum(w['commission'] for w in sorted_weeks)
    ytd_producer_payment = sum(w['producer_payment'] for w in sorted_weeks)

    return render(
        request,
        'marketplace/payment_settlements.html',
        {
            'weeks': sorted_weeks,
            'ytd_gross': ytd_gross,
            'ytd_commission': ytd_commission,
            'ytd_producer_payment': ytd_producer_payment,
        }
    )


# DOWNLOAD SETTLEMENT PDF VIEW - GENERATES A PDF REPORT FOR A SPECIFIC WEEK
@login_required
def download_settlement_pdf(request, week_start_str):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    try:
        week_start = date.fromisoformat(week_start_str)
    except ValueError:
        return redirect('payment_settlements')

    week_end = week_start + timedelta(days=6)

    order_items = OrderItem.objects.filter(
        product__producer=producer_profile,
        order__status='DELIVERED',
        order__created_at__date__gte=week_start,
        order__created_at__date__lte=week_end,
    ).select_related('order__customer', 'product')

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="settlement_{week_start_str}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    y = height - 50

    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, y, "Bristol Regional Food Network")
    y -= 25
    p.setFont("Helvetica", 12)
    p.drawString(50, y, "Weekly Payment Settlement Report")
    y -= 18
    p.drawString(50, y, f"Producer: {producer_profile.business_name}")
    y -= 18
    p.drawString(50, y, f"Week: {week_start.strftime('%d %b %Y')} - {week_end.strftime('%d %b %Y')}")
    y -= 30

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Order #")
    p.drawString(110, y, "Date")
    p.drawString(190, y, "Product")
    p.drawString(340, y, "Qty")
    p.drawString(380, y, "Subtotal")
    p.drawString(450, y, "Commission")
    p.drawString(530, y, "You Receive")
    y -= 5
    p.line(50, y, 580, y)
    y -= 18

    gross_total = Decimal('0.00')
    total_commission = Decimal('0.00')
    total_producer = Decimal('0.00')

    p.setFont("Helvetica", 9)
    for item in order_items:
        subtotal = item.get_subtotal()
        commission = round(subtotal * Decimal('0.05'), 2)
        producer_payment = round(subtotal * Decimal('0.95'), 2)

        gross_total += subtotal
        total_commission += commission
        total_producer += producer_payment

        p.drawString(50, y, f"#{item.order.id}")
        p.drawString(110, y, item.order.created_at.strftime('%d %b'))
        p.drawString(190, y, item.product.name[:20])
        p.drawString(340, y, str(item.quantity))
        p.drawString(380, y, f"£{subtotal}")
        p.drawString(450, y, f"£{commission}")
        p.drawString(530, y, f"£{producer_payment}")
        y -= 16

        if y < 80:
            p.showPage()
            y = height - 50

    y -= 10
    p.line(50, y, 580, y)
    y -= 20
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, y, f"Gross Total: £{gross_total}")
    y -= 18
    p.drawString(50, y, f"Network Commission (5%): £{total_commission}")
    y -= 18
    p.drawString(50, y, f"Your Payment (95%): £{total_producer}")

    p.showPage()
    p.save()
    return response


# SETUP RECURRING ORDER VIEW - STORES RECURRING ORDER DETAILS IN SESSION AND DIRECTS BACK TO BASKET FOR PAYMENT
@login_required
def setup_recurring_order(request):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    basket_items = BasketItem.objects.filter(
        customer=customer_profile
    ).select_related('product')

    if not basket_items.exists():
        messages.error(request, 'Your basket is empty.')
        return redirect('view_basket')

    if request.method == 'POST':
        frequency = request.POST.get('frequency')
        delivery_address = request.POST.get('delivery_address')
        locked_next_order_date = request.POST.get('locked_next_order_date', '').strip()

        if not locked_next_order_date:
            messages.error(
                request,
                'Please choose a preferred delivery date on the basket page before setting up a recurring order.'
            )
            return redirect('view_basket')

        valid_frequencies = [choice[0] for choice in RecurringOrder.FREQUENCY_CHOICES]
        if frequency not in valid_frequencies:
            messages.error(request, 'Invalid frequency selected.')
            return redirect(request.get_full_path())

        try:
            next_order_date = date.fromisoformat(locked_next_order_date)
        except ValueError:
            messages.error(
                request,
                'The selected preferred delivery date is invalid. Please pick the date again on the basket page.'
            )
            return redirect('view_basket')

        if next_order_date < date.today() + timedelta(days=2):
            messages.error(
                request,
                'Recurring orders require first delivery at least 48 hours from now. Please choose a later preferred delivery date in checkout.'
            )
            return redirect('view_basket')

        # STORE THE RECURRING ORDER DETAILS IN THE SESSION
        request.session['recurring_order_data'] = {
            'frequency': frequency,
            'delivery_address': delivery_address,
            'next_order_date': next_order_date.isoformat(),
        }
        
        messages.success(
            request,
            'Recurring order details saved. Please complete payment to confirm your recurring order.'
        )
        return redirect('view_basket')

    preferred_delivery_date = request.GET.get('preferred_delivery_date', '').strip()
    try:
        prefilled_first_delivery_date = date.fromisoformat(preferred_delivery_date).isoformat() if preferred_delivery_date else ''
    except ValueError:
        prefilled_first_delivery_date = ''

    if not prefilled_first_delivery_date:
        messages.error(
            request,
            'Please select a preferred delivery date in checkout before setting up a recurring order.'
        )
        return redirect('view_basket')

    return render(
        request,
        'marketplace/setup_recurring_order.html',
        {
            'basket_items': basket_items,
            'frequency_choices': RecurringOrder.FREQUENCY_CHOICES,
            'delivery_address': customer_profile.address,
            'min_date': (date.today() + timedelta(days=2)).isoformat(),
            'prefilled_first_delivery_date': prefilled_first_delivery_date,
        }
    )


# CANCEL RECURRING ORDER SETUP VIEW - CANCELS AN IN-PROGRESS RECURRING ORDER SETUP
@login_required
def cancel_recurring_setup(request):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    # REMOVE THE RECURRING ORDER DATA FROM THE SESSION
    if 'recurring_order_data' in request.session:
        del request.session['recurring_order_data']
        messages.info(request, 'Recurring order setup cancelled.')
    
    return redirect('view_basket')


# CANCEL RECURRING ORDER DUE TO DATE CHANGE - CLEARS SESSION AND SHOWS RELEVANT MESSAGE
@login_required
def cancel_recurring_for_date_update(request):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    if request.method == 'POST':
        if 'recurring_order_data' in request.session:
            del request.session['recurring_order_data']
        messages.warning(request, 'Recurring order cancelled due to updated delivery date.')

    return redirect('view_basket')


# MANAGE RECURRING ORDERS VIEW - DISPLAYS ALL RECURRING ORDERS FOR THE CUSTOMER
@login_required
def manage_recurring_orders(request):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    recurring_orders = RecurringOrder.objects.filter(
        customer=customer_profile
    ).prefetch_related('items__product', 'upcoming_items__product').order_by('-created_at')

    for recurring_order in recurring_orders:
        overrides = {
            item.product_id: item.quantity
            for item in recurring_order.upcoming_items.filter(
                scheduled_for=recurring_order.next_order_date
            )
        }

        recurring_order.next_order_items = []
        for item in recurring_order.items.all():
            override_quantity = overrides.get(item.product_id)
            quantity = override_quantity if override_quantity is not None else item.quantity
            recurring_order.next_order_items.append(
                {
                    'product': item.product,
                    'template_quantity': item.quantity,
                    'quantity': quantity,
                    'has_override': override_quantity is not None,
                }
            )

    return render(
        request,
        'marketplace/manage_recurring_orders.html',
        {'recurring_orders': recurring_orders}
    )


# UPDATE RECURRING ORDER STATUS VIEW - ALLOWS CUSTOMERS TO PAUSE OR CANCEL RECURRING ORDERS
@login_required
def update_recurring_order_status(request, recurring_order_id):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    recurring_order = get_object_or_404(
        RecurringOrder,
        id=recurring_order_id,
        customer=customer_profile
    )

    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = [choice[0] for choice in RecurringOrder.STATUS_CHOICES]
        if new_status in valid_statuses:
            recurring_order.status = new_status
            recurring_order.save()
            messages.success(request, f'Recurring order {new_status.lower()} successfully.')

    return redirect('manage_recurring_orders')


@login_required
def update_recurring_order_next_order(request, recurring_order_id):
    customer_profile = _get_logged_in_customer(request.user)
    if customer_profile is None:
        return redirect('home')

    recurring_order = get_object_or_404(
        RecurringOrder,
        id=recurring_order_id,
        customer=customer_profile,
    )

    if request.method == 'POST':
        scheduled_for = recurring_order.next_order_date
        existing_overrides = {
            item.product_id: item
            for item in recurring_order.upcoming_items.filter(scheduled_for=scheduled_for)
        }

        for item in recurring_order.items.select_related('product').all():
            quantity_key = f'quantity_{item.product_id}'
            raw_quantity = request.POST.get(quantity_key, str(item.quantity)).strip()

            try:
                new_quantity = int(raw_quantity)
            except ValueError:
                messages.error(request, f'Invalid quantity for {item.product.name}.')
                return redirect('manage_recurring_orders')

            if new_quantity < 0:
                messages.error(request, f'Quantity cannot be negative for {item.product.name}.')
                return redirect('manage_recurring_orders')

            if new_quantity == item.quantity:
                existing_override = existing_overrides.get(item.product_id)
                if existing_override:
                    existing_override.delete()
                continue

            recurring_order.upcoming_items.update_or_create(
                product=item.product,
                scheduled_for=scheduled_for,
                defaults={'quantity': new_quantity},
            )

        messages.success(request, 'Next order quantities updated successfully.')

    return redirect('manage_recurring_orders')


# NOTIFICATIONS VIEW - DISPLAYS ALL NOTIFICATIONS FOR THE LOGGED-IN USER
@login_required
def notifications(request):
    user_notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')

    # MARK ALL AS READ WHEN VIEWED
    user_notifications.filter(is_read=False).update(is_read=True)

    return render(
        request,
        'marketplace/notifications.html',
        {'notifications': user_notifications}
    )


@login_required
def add_recipe(request):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    producer_recipes = Recipe.objects.filter(producer=producer_profile).prefetch_related('images').order_by('-created_at')

    if request.method == 'POST':
        form = RecipeForm(producer=producer_profile, data=request.POST, files=request.FILES)
        if form.is_valid():
            recipe = form.save(commit=False)
            recipe.producer = producer_profile
            recipe.save()
            form.save_m2m()

            for uploaded_image in form.cleaned_data.get('images', []):
                RecipeImage.objects.create(recipe=recipe, image=uploaded_image)

            messages.success(request, f'Recipe "{recipe.title}" added successfully.')
            return redirect('add_recipe')
    else:
        form = RecipeForm(producer=producer_profile)

    return render(
        request,
        'marketplace/producer_add_recipe.html',
        {
            'form': form,
            'producer_recipes': producer_recipes,
        }
    )


# PRODUCER - EDIT RECIPE VIEW
@login_required
def edit_recipe(request, recipe_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    recipe = get_object_or_404(Recipe, id=recipe_id, producer=producer_profile)

    if request.method == 'POST':
        form = RecipeForm(producer=producer_profile, data=request.POST, files=request.FILES, instance=recipe)
        if form.is_valid():
            form.save()

            for uploaded_image in form.cleaned_data.get('images', []):
                RecipeImage.objects.create(recipe=recipe, image=uploaded_image)

            messages.success(request, f'Recipe "{recipe.title}" updated successfully.')
            return redirect('add_recipe')
    else:
        form = RecipeForm(producer=producer_profile, instance=recipe)

    return render(
        request,
        'marketplace/producer_edit_recipe.html',
        {
            'form': form,
            'recipe': recipe,
        }
    )


# PRODUCER - DELETE RECIPE VIEW
@login_required
def delete_recipe(request, recipe_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    recipe = get_object_or_404(Recipe, id=recipe_id, producer=producer_profile)

    if request.method == 'POST':
        recipe.delete()
        messages.success(request, f'Recipe "{recipe.title}" deleted.')

    return redirect('add_recipe')


# CUSTOMER - VIEW ALL RECIPES
@login_required
def recipe_list(request):
    season_input = request.GET.get('season', '').strip()
    recipes = Recipe.objects.select_related('producer').prefetch_related('images').order_by('-created_at')

    valid_seasons = {choice[0] for choice in Recipe.SEASON_CHOICES}
    if season_input in valid_seasons:
        recipes = recipes.filter(seasonal_tag=season_input)

    return render(
        request,
        'marketplace/recipe_list.html',
        {
            'recipes': recipes,
            'season_choices': Recipe.SEASON_CHOICES,
            'selected_season': season_input,
        }
    )


# CUSTOMER - VIEW SINGLE RECIPE
@login_required
def recipe_detail(request, recipe_id):
    recipe = get_object_or_404(Recipe.objects.prefetch_related('images'), id=recipe_id)
    linked_products = recipe.linked_products.all()

    return render(
        request,
        'marketplace/recipe_detail.html',
        {
            'recipe': recipe,
            'linked_products': linked_products,
        }
    )


@login_required
def add_farm_story(request):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    producer_stories = FarmStory.objects.filter(producer=producer_profile)

    if request.method == 'POST':
        form = FarmStoryForm(request.POST)
        if form.is_valid():
            story = form.save(commit=False)
            story.producer = producer_profile
            story.save()
            messages.success(request, f'Farm story "{story.title}" saved successfully.')
            return redirect('add_farm_story')
    else:
        form = FarmStoryForm()

    return render(
        request,
        'marketplace/producer_add_farm_story.html',
        {
            'form': form,
            'producer_stories': producer_stories,
        }
    )


@login_required
def edit_farm_story(request, story_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    story = get_object_or_404(FarmStory, id=story_id, producer=producer_profile)

    if request.method == 'POST':
        form = FarmStoryForm(request.POST, instance=story)
        if form.is_valid():
            form.save()
            messages.success(request, f'Farm story "{story.title}" updated.')
            return redirect('add_farm_story')
    else:
        form = FarmStoryForm(instance=story)

    return render(
        request,
        'marketplace/producer_edit_farm_story.html',
        {
            'form': form,
            'story': story,
        }
    )


@login_required
def delete_farm_story(request, story_id):
    producer_profile = _get_logged_in_producer(request.user)
    if producer_profile is None:
        return redirect('home')

    story = get_object_or_404(FarmStory, id=story_id, producer=producer_profile)

    if request.method == 'POST':
        story.delete()
        messages.success(request, f'Farm story "{story.title}" deleted.')

    return redirect('add_farm_story')


@login_required
def farm_story_list(request):
    stories = FarmStory.objects.filter(published=True).select_related('producer')
    return render(
        request,
        'marketplace/farm_story_list.html',
        {'stories': stories}
    )


@login_required
def farm_story_detail(request, story_id):
    story = get_object_or_404(
        FarmStory.objects.select_related('producer'),
        id=story_id,
        published=True,
    )
    return render(
        request,
        'marketplace/farm_story_detail.html',
        {'story': story}
    )
# ADMIN REPORT PDF EXPORT VIEW - GENERATES A PDF VERSION OF A SELECTED REPORT
@login_required
def download_admin_report_pdf(request):
    if not _is_admin_user(request.user):
        return redirect('home')

    report_type = request.GET.get('report_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    parsed_from = _parse_report_date(date_from)
    parsed_to = _parse_report_date(date_to)
    report_data = _build_admin_report_data(report_type, parsed_from, parsed_to)

    if report_data is None:
        return redirect('admin_reports')

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="admin_report_{report_type}.pdf"'

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    y = height - 50

    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, y, "Bristol Regional Food Network")
    y -= 25
    p.setFont("Helvetica", 12)
    p.drawString(50, y, "Admin Report")
    y -= 18
    p.drawString(50, y, f"Type: {report_type.replace('_', ' ').title()}")
    y -= 18
    period_label = f"{date_from or 'beginning'} to {date_to or 'present'}" if (date_from or date_to) else "All time"
    p.drawString(50, y, f"Period: {period_label}")
    y -= 30

    p.setFont("Helvetica-Bold", 11)
    if report_data['type'] == 'financial':
        p.drawString(50, y, "Total Sales")
        p.drawString(280, y, f"£{report_data['total_sales']}")
        y -= 20
        p.drawString(50, y, "Commission Earned (5%)")
        p.drawString(280, y, f"£{report_data['total_commission']}")
        y -= 20
        p.drawString(50, y, "Producer Payouts (95%)")
        p.drawString(280, y, f"£{report_data['total_producer_payouts']}")
        y -= 20
        p.drawString(50, y, "Orders")
        p.drawString(280, y, f"{report_data['order_count']}")
        y -= 20
        p.drawString(50, y, "Average Order Value")
        p.drawString(280, y, f"£{report_data['average_order_value']}")
    else:
        p.drawString(50, y, "Total Accounts")
        p.drawString(280, y, f"{report_data['total_accounts']}")
        y -= 20
        p.drawString(50, y, "New Accounts (in period)")
        p.drawString(280, y, f"{report_data['new_accounts']}")
        y -= 20
        p.drawString(50, y, "Products Listed")
        p.drawString(280, y, f"{report_data['total_products']}")
        y -= 20
        p.drawString(50, y, "Orders Placed")
        p.drawString(280, y, f"{report_data['total_orders']}")

    p.showPage()
    p.save()
    return response
