
# Generated by Django 1.10.5 on 2017-02-06 12:01
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("product", "0030_auto_20170206_0407")]

    operations = [
        migrations.RemoveField(model_name="product", name="weight"),
        migrations.RemoveField(model_name="productvariant", name="weight_override"),
    ]