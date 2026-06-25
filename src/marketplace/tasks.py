from datetime import date, timedelta

from celery import shared_task
from django.contrib.auth.models import User
from django.db import transaction

from .models import CustomerOrder, Notification, OrderItem, RecurringOrder, RecurringOrderUpcomingItem


# GENERIC NOTIFICATION TASK - CREATES A NOTIFICATION ROW FOR THE GIVEN USER
@shared_task
def create_notification(user_id, message):
    user = User.objects.get(id=user_id)
    Notification.objects.create(user=user, message=message)


def _advance_recurring_date(current_date, frequency):
    # ADVANCE THE NEXT ORDER DATE BASED ON THE RECURRING FREQUENCY
    if frequency == 'WEEKLY':
        return current_date + timedelta(days=7)

    if frequency == 'FORTNIGHTLY':
        return current_date + timedelta(days=14)

    if frequency == 'MONTHLY':
        month = current_date.month + 1
        year = current_date.year
        if month > 12:
            month = 1
            year += 1

        if month == 2:
            is_leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            max_day = 29 if is_leap else 28
        elif month in (4, 6, 9, 11):
            max_day = 30
        else:
            max_day = 31

        return date(year, month, min(current_date.day, max_day))

    return current_date + timedelta(days=7)


def _calculate_delivery_date(order_run_date, delivery_week_offset, delivery_day):
    # MAP THE RUN DATE TO ITS DELIVERY DATE USING THE STORED SAME-WEEK/NEXT-WEEK SLOT
    run_weekday = order_run_date.weekday()

    if delivery_week_offset == 0:
        day_gap = delivery_day - run_weekday
        if day_gap < 0:
            day_gap += 7
    else:
        day_gap = (7 - run_weekday) + delivery_day

    return order_run_date + timedelta(days=day_gap)


def _get_effective_recurring_items(recurring_order, scheduled_for):
    # APPLY NEXT-ORDER OVERRIDES ON TOP OF TEMPLATE ITEMS FOR THE SCHEDULED DATE
    overrides = {
        override.product_id: override.quantity
        for override in recurring_order.upcoming_items.filter(scheduled_for=scheduled_for)
    }

    effective_items = []
    for item in recurring_order.items.select_related('product__producer__user').all():
        quantity = overrides.get(item.product_id, item.quantity)
        if quantity > 0:
            effective_items.append((item.product, quantity))

    return effective_items


@shared_task
def process_due_recurring_orders():
    # CREATE REAL DELIVERED ORDERS FOR ALL ACTIVE RECURRING TEMPLATES DUE TODAY OR EARLIER
    today = date.today()
    due_orders = RecurringOrder.objects.filter(
        status='ACTIVE',
        next_order_date__lte=today,
    ).select_related('customer__user').prefetch_related('items__product__producer__user', 'upcoming_items')

    created_count = 0

    for recurring_order in due_orders:
        scheduled_for = recurring_order.next_order_date
        delivery_date = _calculate_delivery_date(
            scheduled_for,
            recurring_order.delivery_week_offset,
            recurring_order.delivery_day,
        )

        if CustomerOrder.objects.filter(
            source_recurring_order=recurring_order,
            source_scheduled_for=scheduled_for,
        ).exists():
            recurring_order.next_order_date = _advance_recurring_date(scheduled_for, recurring_order.frequency)
            recurring_order.save(update_fields=['next_order_date'])
            continue

        effective_items = _get_effective_recurring_items(recurring_order, scheduled_for)
        if not effective_items:
            recurring_order.next_order_date = _advance_recurring_date(scheduled_for, recurring_order.frequency)
            recurring_order.save(update_fields=['next_order_date'])
            continue

        insufficient_stock_products = [
            f'{product.name} ({product.stock_quantity} left)'
            for product, quantity in effective_items
            if quantity > product.stock_quantity
        ]
        if insufficient_stock_products:
            create_notification.delay(
                recurring_order.customer.user.id,
                (
                    f'Recurring order due on {scheduled_for} could not be processed because stock was too low for: '
                    f'{", ".join(insufficient_stock_products)}.'
                )
            )
            continue

        producer_notifications = {}
        total_price = sum(product.discounted_price * quantity for product, quantity in effective_items)

        with transaction.atomic():
            order = CustomerOrder.objects.create(
                customer=recurring_order.customer,
                source_recurring_order=recurring_order,
                source_scheduled_for=scheduled_for,
                delivery_address=recurring_order.delivery_address,
                preferred_delivery_date=delivery_date,
                card_holder_name='Recurring Checkout',
                card_number_last4='4242',
                total_price=total_price,
                status='DELIVERED',
            )

            for product, quantity in effective_items:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=product.discounted_price,
                )

                product.stock_quantity -= quantity
                product.save(update_fields=['stock_quantity'])

                lines = producer_notifications.setdefault(product.producer.user_id, [])
                lines.append(f'{quantity}x {product.name}')

            RecurringOrderUpcomingItem.objects.filter(
                recurring_order=recurring_order,
                scheduled_for=scheduled_for,
            ).delete()

            recurring_order.next_order_date = _advance_recurring_date(scheduled_for, recurring_order.frequency)
            recurring_order.save(update_fields=['next_order_date'])

        create_notification.delay(
            recurring_order.customer.user.id,
            (
                f'Recurring order #{order.id} has been processed on {scheduled_for} for delivery {delivery_date}. '
                f'Receipt total: £{order.total_price}.'
            )
        )

        for producer_user_id, lines in producer_notifications.items():
            create_notification.delay(
                producer_user_id,
                (
                    f'Recurring order #{order.id} has been settled and delivered for {delivery_date}: '
                    f'{", ".join(lines)}.'
                )
            )

        created_count += 1

    return {'created_count': created_count}
