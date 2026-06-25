from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    # DEPENDS ON THE PREVIOUS MIGRATION THAT ADDED THE PRODUCER BIO FIELD
    dependencies = [
        ('marketplace', '0005_producer_bio'),
    ]

    operations = [
        # CREATE THE BASKET ITEM TABLE TO HOLD PRODUCTS IN A CUSTOMER'S BASKET
        migrations.CreateModel(
            name='BasketItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                # TIMESTAMP FOR WHEN THE ITEM WAS ADDED TO THE BASKET
                ('added_at', models.DateTimeField(auto_now_add=True)),
                # QUANTITY OF THE PRODUCT THE CUSTOMER WANTS
                ('quantity', models.PositiveIntegerField(default=1)),
                # FOREIGN KEY TO THE CUSTOMER WHO OWNS THE BASKET
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='basket_items', to='marketplace.customer')),
                # FOREIGN KEY TO THE PRODUCT BEING ADDED
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='basket_items', to='marketplace.product')),
            ],
            options={
                # ENSURE ONLY ONE ENTRY PER CUSTOMER+PRODUCT COMBINATION
                'unique_together': {('customer', 'product')},
            },
        ),
        # CREATE THE CUSTOMER ORDER TABLE TO STORE CONFIRMED ORDERS
        migrations.CreateModel(
            name='CustomerOrder',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                # TIMESTAMP AUTOMATICALLY RECORDED WHEN ORDER IS PLACED
                ('created_at', models.DateTimeField(auto_now_add=True)),
                # DELIVERY ADDRESS PROVIDED BY THE CUSTOMER AT CHECKOUT
                ('delivery_address', models.CharField(max_length=300)),
                # PREFERRED DELIVERY DATE CHOSEN BY THE CUSTOMER
                ('preferred_delivery_date', models.DateField()),
                # CARD HOLDER NAME FOR REFERENCE ONLY
                ('card_holder_name', models.CharField(max_length=100)),
                # ONLY LAST 4 DIGITS STORED - FULL CARD NUMBERS ARE NEVER PERSISTED
                ('card_number_last4', models.CharField(max_length=4)),
                # TOTAL ORDER VALUE CALCULATED AT CHECKOUT
                ('total_price', models.DecimalField(decimal_places=2, max_digits=10)),
                # ORDER STATUS - DEFAULTS TO PENDING WHEN FIRST CREATED
                ('status', models.CharField(
                    choices=[('PENDING', 'Pending'), ('CONFIRMED', 'Confirmed'), ('DELIVERED', 'Delivered')],
                    default='PENDING',
                    max_length=20,
                )),
                # FOREIGN KEY LINKING THE ORDER TO ITS CUSTOMER
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='marketplace.customer')),
            ],
        ),
        # CREATE THE ORDER ITEM TABLE TO STORE INDIVIDUAL PRODUCT LINES WITHIN AN ORDER
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                # QUANTITY OF THE PRODUCT IN THIS ORDER LINE
                ('quantity', models.PositiveIntegerField()),
                # PRICE SNAPSHOTTED AT THE TIME OF PURCHASE
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10)),
                # FOREIGN KEY TO THE PARENT ORDER
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='marketplace.customerorder')),
                # FOREIGN KEY TO THE PRODUCT THAT WAS ORDERED
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='order_items', to='marketplace.product')),
            ],
        ),
    ]
