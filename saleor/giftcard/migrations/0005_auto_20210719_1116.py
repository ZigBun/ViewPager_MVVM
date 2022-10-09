
# Generated by Django 3.2.5 on 2021-07-19 11:16

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import saleor.core.utils.json_serializer


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app", "0004_auto_20210308_1135"),
        ("product", "0146_auto_20210518_0945"),
        ("giftcard", "0004_auto_20200902_1249"),
    ]

    operations = [
        migrations.AddField(
            model_name="giftcard",
            name="app",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="app.app",
            ),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="created_by_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="expiry_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="expiry_period",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="expiry_period_type",
            field=models.CharField(
                blank=True,
                choices=[("day", "day"), ("month", "Month"), ("year", "Year")],
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="expiry_type",
            field=models.CharField(
                choices=[
                    ("never_expire", "Never expire"),
                    ("expiry_period", "Expiry period"),
                    ("expiry_date", "Expiry date"),
                ],
                default="expiry_date",
                max_length=32,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="giftcard",
            name="metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                encoder=saleor.core.utils.json_serializer.CustomJsonEncoder,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="private_metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                encoder=saleor.core.utils.json_serializer.CustomJsonEncoder,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gift_cards",
                to="product.product",
            ),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="tag",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="used_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gift_cards",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="giftcard",
            name="used_by_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name="giftcard",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="user_gift_cards",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name="giftcard",
            name="start_date",
        ),
        migrations.AddIndex(
            model_name="giftcard",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["private_metadata"], name="giftcard_p_meta_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="giftcard",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["metadata"], name="giftcard_meta_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="giftcard",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["tag"], name="giftcard_search_gin", opclasses=["gin_trgm_ops"]
            ),
        ),
        migrations.CreateModel(
            name="GiftCardEvent",
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
                    "date",
                    models.DateTimeField(
                        default=django.utils.timezone.now, editable=False
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            (
                                "issued",
                                "The gift card was created be staff user or app.",
                            ),
                            ("bought", "The gift card was bought by customer."),
                            ("updated", "The gift card was updated."),
                            ("activated", "The gift card was activated."),
                            ("deactivated", "The gift card was deactivated."),
                            ("balance_reset", "The gift card balance was reset."),
                            (
                                "expiry_settings_updated",
                                "The gift card expiry settings was updated.",
                            ),
                            (
                                "sent_to_customer",
                                "The gift card was sent to the customer.",
                            ),
                            ("resent", "The gift card was resent to the customer."),
                        ],
                        max_length=255,
                    ),
                ),
                (
                    "parameters",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=saleor.core.utils.json_serializer.CustomJsonEncoder,
                    ),
                ),
                (
                    "app",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gift_card_events",
                        to="app.app",
                    ),
                ),
                (
                    "gift_card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="giftcard.giftcard",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gift_card_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("date",)},
        ),
    ]