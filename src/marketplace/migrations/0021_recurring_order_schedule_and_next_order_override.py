from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0020_merge_20260424_0001'),
    ]

    operations = [
        migrations.AddField(
            model_name='recurringorder',
            name='delivery_week_offset',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='RecurringOrderUpcomingItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scheduled_for', models.DateField()),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('product', models.ForeignKey(on_delete=models.deletion.CASCADE, to='marketplace.product')),
                ('recurring_order', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='upcoming_items', to='marketplace.recurringorder')),
            ],
            options={
                'unique_together': {('recurring_order', 'product', 'scheduled_for')},
            },
        ),
    ]