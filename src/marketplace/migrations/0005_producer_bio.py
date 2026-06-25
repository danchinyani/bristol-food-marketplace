from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0004_rename_organic_certified_product_is_organic_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='producer',
            name='bio',
            field=models.TextField(blank=True),
        ),
    ]
