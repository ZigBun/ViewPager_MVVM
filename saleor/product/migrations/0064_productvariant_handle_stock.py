
# Generated by Django 2.0.3 on 2018-06-03 11:52

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("product", "0063_required_attr_value_order")]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="track_inventory",
            field=models.BooleanField(default=True),
        )
    ]