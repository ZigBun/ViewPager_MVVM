
# Generated by Django 3.2.13 on 2022-04-29 09:07

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("warehouse", "0024_rewrite_order_line_relations"),
    ]

    operations = [
        migrations.AddField(
            model_name="preorderreservation",
            name="checkout_line_token",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="checkout_line_token",
            field=models.UUIDField(null=True),
        ),
    ]