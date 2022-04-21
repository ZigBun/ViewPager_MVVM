
# Generated by Django 3.2.13 on 2022-04-29 09:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0026_fulfill_checkout_line_token_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="preorderreservation",
            name="checkout_line",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="preorder_reservations",
                to="checkout.checkoutline",
                to_field="old_id",
            ),
        ),
        migrations.AlterField(
            model_name="reservation",
            name="checkout_line",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reservations",
                to="checkout.checkoutline",
                to_field="old_id",
            ),
        ),
    ]