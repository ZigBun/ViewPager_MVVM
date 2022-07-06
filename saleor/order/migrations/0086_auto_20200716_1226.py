# Generated by Django 3.0.6 on 2020-07-16 12:26

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0085_delete_invoice"),
    ]

    operations = [
        migrations.AlterField(
            model_name="orderevent",
            name="type",
            field=models.CharField(
                choices=[
                    ("DRAFT_CREATED", "draft_created"),
                    ("DRAFT_ADDED_PRODUCTS", "draft_added_products"),
                    ("DRAFT_REMOVED_PRODUCTS", "draft_removed_products"),
                    ("PLACED", "placed"),
                    ("PLACED_FROM_DRAFT", "placed_from_draft"),
                    ("OVERSOLD_ITEMS", "oversold_items"),
                    ("CANCELED", "canceled"),
                    ("ORDER_MARKED_AS_PAID", "order_marked_as_paid"),
 