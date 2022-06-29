
# Generated by Django 3.2.5 on 2021-07-28 07:52

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0147_auto_20210817_1015"),
    ]

    operations = [
        migrations.AddField(
            model_name="producttype",
            name="kind",
            field=models.CharField(
                choices=[
                    ("normal", "A standard product type."),
                    ("gift_card", "A gift card product type."),
                ],
                default="normal",
                max_length=32,
            ),
            preserve_default=False,
        ),
    ]