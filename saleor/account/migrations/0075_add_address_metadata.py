# Generated by Django 3.2.16 on 2023-01-10 08:39

import django.contrib.postgres.indexes
from django.db import migrations, models
import saleor.core.utils.json_serializer


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0074_merge_20230102_0914"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                encoder=saleor.core.utils.json_serializer.CustomJsonEncoder,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="address",
            name="private_metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                encoder=saleor.core.utils.json_serializer.CustomJsonEncoder,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="address",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["private_metadata"], name="address_p_meta_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="address",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["metadata"], name="address_meta_idx"
            ),
        ),
    ]
