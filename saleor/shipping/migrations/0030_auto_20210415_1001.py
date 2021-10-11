
# Generated by Django 3.1.7 on 2021-04-15 10:01

from django.db import migrations

import saleor.core.db.fields
import saleor.core.utils.editorjs


class Migration(migrations.Migration):
    dependencies = [
        ("shipping", "0029_shippingzone_channels"),
    ]

    operations = [
        migrations.AddField(
            model_name="shippingmethod",
            name="description",
            field=saleor.core.db.fields.SanitizedJSONField(
                blank=True,
                null=True,
                sanitizer=saleor.core.utils.editorjs.clean_editor_js,
            ),
        ),
        migrations.AddField(
            model_name="shippingmethodtranslation",
            name="description",
            field=saleor.core.db.fields.SanitizedJSONField(
                blank=True,
                null=True,
                sanitizer=saleor.core.utils.editorjs.clean_editor_js,
            ),
        ),
    ]