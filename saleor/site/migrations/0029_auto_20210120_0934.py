
# Generated by Django 3.1.4 on 2021-01-20 09:34

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("site", "0028_delete_authorizationkey"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="default_weight_unit",
            field=models.CharField(
                choices=[
                    ("g", "Gram"),
                    ("lb", "Pound"),
                    ("oz", "Ounce"),
                    ("kg", "kg"),
                    ("tonne", "Tonne"),
                ],
                default="kg",
                max_length=30,
            ),
        ),
    ]