
# Generated by Django 3.0.6 on 2020-08-20 10:50

import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify


def migrate_variant_price_data(apps, schema_editor):
    Channel = apps.get_model("channel", "Channel")
    ProductVariant = apps.get_model("product", "ProductVariant")
    ProductVariantChannelListing = apps.get_model(
        "product", "ProductVariantChannelListing"
    )

    if ProductVariant.objects.exists():
        channels_dict = {}

        for variant in ProductVariant.objects.iterator():
            currency = variant.currency
            channel = channels_dict.get(currency)
            if not channel:
                name = f"Channel {currency}"
                channel, _ = Channel.objects.get_or_create(
                    currency_code=currency,
                    defaults={"name": name, "slug": slugify(name)},
                )
                channels_dict[currency] = channel
            ProductVariantChannelListing.objects.create(
                variant=variant,
                channel=channel,
                currency=currency,
                price_amount=variant.price_amount,
                cost_price_amount=variant.cost_price_amount,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("channel", "0001_initial"),
        ("checkout", "0030_checkout_channel_listing"),
        ("product", "0132_product_rating"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductVariantChannelListing",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "currency",
                    models.CharField(
                        max_length=3,
                    ),
                ),
                ("price_amount", models.DecimalField(decimal_places=3, max_digits=12)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="variant_listings",
                        to="channel.Channel",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channel_listings",
                        to="product.ProductVariant",
                    ),
                ),
                (
                    "cost_price_amount",
                    models.DecimalField(
                        blank=True, decimal_places=3, max_digits=12, null=True
                    ),
                ),
            ],
            options={"ordering": ("pk",), "unique_together": {("variant", "channel")}},
        ),
        migrations.RunPython(migrate_variant_price_data),
        migrations.RemoveField(
            model_name="productvariant",
            name="price_amount",
        ),
        migrations.RemoveField(
            model_name="productvariant",
            name="cost_price_amount",
        ),
        migrations.RemoveField(
            model_name="productvariant",
            name="currency",
        ),
    ]