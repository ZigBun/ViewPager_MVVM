
# Generated by Django 3.1.2 on 2020-11-17 12:32

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("site", "0026_remove_sitesettings_homepage_collection"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="automatically_confirm_all_new_orders",
            field=models.BooleanField(default=True),
        ),
    ]