# Generated by Django 1.10.3 on 2016-12-07 14:44
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("product", "0017_remove_stock_location")]

    operations = [
        migrations.RenameField(
            model_name="stock", old_name="location_link", new_name="location"
        ),
        migrations.AlterUniqueTogether(
            name="stock", unique_together=set([("variant", "location")])
        ),
    ]
