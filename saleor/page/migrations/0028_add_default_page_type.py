
# Generated by Django 3.2.16 on 2022-12-20 14:39

from django.db import migrations
from django.conf import settings


def create_default_page_type(apps, schema_editor):
    PageType = apps.get_model("page", "PageType")
    if not PageType.objects.all().exists() and settings.POPULATE_DEFAULTS:
        PageType.objects.create(name="Default Type", slug="default-type")


class Migration(migrations.Migration):
    dependencies = [
        ("page", "0027_alter_page_created_at"),
    ]

    operations = [
        migrations.RunPython(create_default_page_type, migrations.RunPython.noop),
    ]