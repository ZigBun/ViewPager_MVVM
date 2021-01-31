
# Generated by Django 3.1.3 on 2020-12-29 11:26

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0095_auto_20201229_1014"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="shipping_tax_rate",
            field=models.DecimalField(
                decimal_places=4, default=Decimal("0.0"), max_digits=5
            ),
        ),
    ]