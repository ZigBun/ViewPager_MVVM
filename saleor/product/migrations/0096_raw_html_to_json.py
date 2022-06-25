# Generated by Django 2.2.3 on 2019-07-15 07:47
from django.db import migrations
from draftjs_sanitizer import clean_draft_js
from html_to_draftjs import html_to_draftjs

from ...core.db.fields import SanitizedJSONField
from ...core.utils.draftjs import json_content_to_raw_text


def convert_products_html_to_json(apps, schema_editor):
    Product = apps.get_model("product", "Product")
    qs = Product.objects.all()

    for product in qs:
        description_json = product.description_json
        description_raw = json_content_to_raw_text(description_json)

        # Override the JSON description if there was nothing in it
        if not description_raw.strip():
            product.description_json = html_to_draftjs(product.description)
            product.save(update_fields=["description_json"])

    ProductTranslation = apps.get_model("product", "ProductTranslation")
    qs = ProductTranslation.objects.all()

    for translation in qs:
        description_json = translation.description_json
        description_raw = json_content_to_raw_text(description_json)

        # Override the JSON description if there was nothing in it
        if not description_raw:
            translation.description_json = html_to_draftjs(translation.description)
            translation.save(update_fields=["description_json"])


def sanitize_descriptions_json(apps, schema_editor):
    Product = apps.get_model("product", "Product")
    qs = Product.objects.all()

    for product in qs:
        product.description_json = clean_draft_js(product.description_jso