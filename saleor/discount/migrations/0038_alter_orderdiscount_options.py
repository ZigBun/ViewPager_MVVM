
# Generated by Django 3.2.13 on 2022-04-11 10:17

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("discount", "0037_rewrite_discount_order_relations"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="orderdiscount",
            options={"ordering": ("pk",)},
        ),
    ]