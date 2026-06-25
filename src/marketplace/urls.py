from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import PasswordChangeView
from django.urls import path, reverse_lazy
from django.conf import settings
from django.core.cache import cache
from .views import CustomPasswordChangeView


# CUSTOM LOGIN VIEW - HANDLES REMEMBER ME CHECKBOX BY TOGGLING SESSION EXPIRY
class RememberMeLoginView(auth_views.LoginView):
    template_name = 'marketplace/login.html'

    def _get_client_ip(self):
        forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return self.request.META.get('REMOTE_ADDR', 'unknown')

    def _get_username(self):
        return self.request.POST.get('username', '').strip().lower()

    def _get_rate_limit_config(self):
        max_attempts = getattr(settings, 'LOGIN_RATE_LIMIT_ATTEMPTS', 5)
        lockout_window_seconds = getattr(settings, 'LOGIN_RATE_LIMIT_WINDOW_SECONDS', 900)
        return max_attempts, lockout_window_seconds

    def _get_lockout_cache_key(self):
        return f'login_lockout:{self._get_client_ip()}:{self._get_username()}'

    def _get_attempts_cache_key(self):
        return f'login_attempts:{self._get_client_ip()}:{self._get_username()}'

    def _is_locked_out(self):
        return cache.get(self._get_lockout_cache_key()) is True

    def post(self, request, *args, **kwargs):
        if self._is_locked_out():
            _max_attempts, lockout_window_seconds = self._get_rate_limit_config()
            lockout_minutes = max(1, lockout_window_seconds // 60)
            form = self.get_form()
            form.add_error(None, f'Account locked, wait {lockout_minutes} minutes')
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        cache.delete(self._get_attempts_cache_key())
        cache.delete(self._get_lockout_cache_key())

        remember_me = self.request.POST.get('remember_me')
        if not remember_me:
            # NO REMEMBER ME - SESSION EXPIRES WHEN BROWSER CLOSES
            self.request.session.set_expiry(0)
        return super().form_valid(form)

    def form_invalid(self, form):
        username = self._get_username()
        if username:
            max_attempts, lockout_window_seconds = self._get_rate_limit_config()
            attempts_key = self._get_attempts_cache_key()
            lockout_key = self._get_lockout_cache_key()

            attempts = cache.get(attempts_key, 0) + 1
            cache.set(attempts_key, attempts, timeout=lockout_window_seconds)

            if attempts >= max_attempts:
                cache.set(lockout_key, True, timeout=lockout_window_seconds)
                cache.delete(attempts_key)
                lockout_minutes = max(1, lockout_window_seconds // 60)
                form.add_error(None, f'Account locked, wait {lockout_minutes} minutes')

        return super().form_invalid(form)


urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/profiles/', views.admin_profiles, name='admin_profiles'),
    path('dashboard/orders/', views.admin_orders, name='admin_orders'),
    path('dashboard/reports/', views.admin_reports, name='admin_reports'),
    path('dashboard/reports/export/pdf/', views.download_admin_report_pdf, name='download_admin_report_pdf'),
    path('signup/', views.signup_choice, name='signup_choice'),
    path('signup/producer/', views.signup_producer, name='signup_producer'),
    path('signup/customer/', views.signup_customer, name='signup_customer'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('login/', RememberMeLoginView.as_view(), name='login'),
    path('account/edit/', views.edit_account, name='edit_account'),
    path('products/add/', views.add_product, name='add_product'),
    path('account/password/',CustomPasswordChangeView.as_view(),name='change_password'),
    path('market/', views.customer_market, name='customer_market'),
    path('producer/bio/', views.producer_bio, name='producer_bio'),
    path('producers/<int:producer_id>/', views.producer_bio_public, name='producer_bio_public'),
    path('products/<int:product_id>/', views.producer_product_actions, name='producer_product_actions'),
    path('products/<int:product_id>/edit/', views.edit_product, name='edit_product'),
    path('products/<int:product_id>/delete/', views.delete_product, name='delete_product'),
    path('basket/add/<int:product_id>/', views.add_to_basket, name='add_to_basket'),
    path('basket/', views.view_basket, name='view_basket'),
    path('basket/remove/<int:item_id>/', views.remove_from_basket, name='remove_from_basket'),
    path('basket/checkout/', views.checkout, name='checkout'),
    path('orders/checkout/stripe/success/', views.stripe_checkout_success, name='stripe_checkout_success'),
    path('orders/<int:order_id>/confirmation/', views.order_confirmation, name='order_confirmation'),
    path('orders/', views.order_history, name='order_history'),
    path('orders/items/<int:order_item_id>/review/', views.submit_product_review, name='submit_product_review'),
    path('orders/<int:order_id>/reorder/', views.reorder, name='reorder'),
    path('orders/<int:order_id>/receipt/', views.download_receipt, name='download_receipt'),
    path('producer/orders/', views.producer_orders, name='producer_orders'),
    path('producer/orders/completed/', views.producer_completed_orders, name='producer_completed_orders'),
    path('producer/reviews/', views.producer_reviews, name='producer_reviews'),
    path('producer/orders/<int:order_id>/update/', views.update_order_status, name='update_order_status'),
    path('producer/settlements/', views.payment_settlements, name='payment_settlements'),
    path('producer/settlements/<str:week_start_str>/pdf/', views.download_settlement_pdf, name='download_settlement_pdf'),
    path('orders/recurring/setup/', views.setup_recurring_order, name='setup_recurring_order'),
    path('orders/recurring/cancel/', views.cancel_recurring_setup, name='cancel_recurring_setup'),
    path('orders/recurring/cancel-date-update/', views.cancel_recurring_for_date_update, name='cancel_recurring_for_date_update'),
    path('orders/recurring/', views.manage_recurring_orders, name='manage_recurring_orders'),
    path('orders/recurring/<int:recurring_order_id>/update/', views.update_recurring_order_status, name='update_recurring_order_status'),
    path('orders/recurring/<int:recurring_order_id>/next-order/update/', views.update_recurring_order_next_order, name='update_recurring_order_next_order'),
    path('notifications/', views.notifications, name='notifications'),
    path('recipes/', views.recipe_list, name='recipe_list'),
    path('recipes/<int:recipe_id>/', views.recipe_detail, name='recipe_detail'),
    path('producer/recipes/', views.add_recipe, name='add_recipe'),
    path('producer/recipes/<int:recipe_id>/edit/', views.edit_recipe, name='edit_recipe'),
    path('producer/recipes/<int:recipe_id>/delete/', views.delete_recipe, name='delete_recipe'),
]