
# Generated by Django 3.2.12 on 2022-02-25 11:08

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0131_change_pk_to_uuid"),
        ("discount", "0036_save_discocunt_order_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="orderdiscount",
            name="order_token",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="order.order",
            ),
        ),
        migrations.RemoveField(
            model_name="orderdiscount",
            name="order",
        ),
        migrations.RenameField(
            model_name="orderdiscount",
            old_name="order_token",
            new_name="order",
        ),
        migrations.AlterField(
            model_name="orderdiscount",
            name="order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="discounts",
                to="order.order",
            ),
        ),
    ]