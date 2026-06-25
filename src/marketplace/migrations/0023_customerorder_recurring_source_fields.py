from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0022_recurringorder_delivery_day_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerorder',
            name='source_recurring_order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_orders', to='marketplace.recurringorder'),
        ),
        migrations.AddField(
            model_name='customerorder',
            name='source_scheduled_for',
            field=models.DateField(blank=True, null=True),
        ),
    ]
