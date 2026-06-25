# CONTEXT PROCESSOR TO MAKE THE BASKET ITEM COUNT AVAILABLE IN EVERY TEMPLATE
# THIS ALLOWS THE BASKET ICON IN THE TOP BAR TO DISPLAY THE CURRENT COUNT GLOBALLY

from .models import BasketItem
from django.conf import settings


def basket_count(request):
    # ONLY COUNT BASKET ITEMS IF THE USER IS AUTHENTICATED
    is_customer = False
    is_producer = False
    is_admin = False

    if request.user.is_authenticated:
        # CHECK IF THE USER IS A STAFF/SUPERUSER (ADMIN)
        is_admin = request.user.is_staff or request.user.is_superuser

        try:
            # ATTEMPT TO GET THE CUSTOMER PROFILE LINKED TO THE LOGGED-IN USER
            customer = request.user.customer
            is_customer = True
            # COUNT THE TOTAL NUMBER OF DISTINCT PRODUCT LINES IN THE BASKET
            count = BasketItem.objects.filter(customer=customer).count()
        except Exception:
            # IF THE USER HAS NO CUSTOMER PROFILE, BASKET COUNT IS ZERO
            count = 0

        try:
            request.user.producer
            is_producer = True
        except Exception:
            is_producer = False
    else:
        # UNAUTHENTICATED USERS HAVE NO BASKET
        count = 0

    stripe_publishable_key = getattr(settings, 'STRIPE_PUBLISHABLE_KEY', '')
    stripe_enabled = bool(stripe_publishable_key)
    stripe_test_mode = stripe_publishable_key.startswith('pk_test_')

    # RETURN SHARED CONTEXT VALUES FOR NAVIGATION + PAYMENT BADGING
    return {
        'basket_count': count,
        'is_customer': is_customer,
        'is_producer': is_producer,
        'is_admin': is_admin,
        'stripe_enabled': stripe_enabled,
        'stripe_test_mode': stripe_test_mode,
    }
