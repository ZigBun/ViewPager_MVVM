# Generated by Django 2.1.7 on 2019-03-25 09:40

import versatileimagefield.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("account", "0025_auto_20190314_0550")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=versatileimagefield.fields.VersatileImageField(
                blank=True, null=True, upload_to="user-avatars"
            ),
        )
    ]
