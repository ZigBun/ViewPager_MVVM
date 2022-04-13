
# Generated by Django 3.2.16 on 2022-10-12 08:35

from django.db import migrations
from django.db.models import F, Func, Value

BATCH_SIZE = 10000


def update_file_urls(apps, schema_editor):
    AttributeValue = apps.get_model("attribute", "AttributeValue")
    queryset = AttributeValue.objects.filter(file_url__startswith="/").order_by("pk")
    for pks in queryset_in_batches(queryset):
        AttributeValue.objects.filter(pk__in=pks).update(
            file_url=Func(F("file_url"), Value("/"), function="ltrim")
        )


def queryset_in_batches(queryset):
    """Slice a queryset into batches.

    Input queryset should be sorted be pk.
    """
    start_pk = 0

    while True:
        qs = queryset.filter(pk__gt=start_pk)[:BATCH_SIZE]
        pks = list(qs.values_list("pk", flat=True))

        if not pks:
            break

        yield pks

        start_pk = pks[-1]


class Migration(migrations.Migration):
    dependencies = [
        ("attribute", "0022_plain_text_attribute"),
    ]

    operations = [
        migrations.RunPython(update_file_urls, reverse_code=migrations.RunPython.noop),
    ]