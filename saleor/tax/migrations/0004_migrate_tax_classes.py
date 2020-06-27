# Generated by Django 3.2.14 on 2022-07-27 16:05

from collections import defaultdict
from django_countries import countries
from django.db import migrations
from django.db.models import Q


AVATAX_CODE_META_KEY = "avatax.code"
AVATAX_DESCRIPTION_META_KEY = "avatax.description"
VATLAYER_CODE_META_KEY = "vatlayer.code"

# Non-taxable product's tax code for Avalara.
TAX_CODE_NON_TAXABLE_PRODUCT = "NT"

TAX_CLASS_ZERO_RATE = "No Taxes"

AVATAX_PLUGIN_ID = "mirumee.taxes.avalara"

BATCH_SIZE = 500


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


def _populate_tax_class_name_and_metadata(obj):
    avatax_code = obj.metadata.get(AVATAX_CODE_META_KEY)
    avatax_description = obj.metadata.get(AVATAX_DESCRIPTION_META_KEY)
    vatlayer_code = obj.metadata.get(VATLAYER_CODE_META_KEY)

    name = None
    metadata = {}

    if avatax_code:
        name = avatax_description or avatax_code
        metadata = {
            AVATAX_CODE_META_KEY: avatax_code,
            AVATAX_DESCRIPTION_META_KEY: avatax_description or "",
        }
    elif vatlayer_code:
        name = vatlayer_code
        metadata = {VATLAYER_CODE_META_KEY: vatlayer_code}

    return name, metadata


def migrate_product_tax_codes(apps, _schema_editor):
    """Create tax classes by migrating currently used tax codes.

    Tax codes are stored in metadata of products and product types. For each found code
    we get or create a TaxClass instance and assign the object to the tax class.
    If object has both Avalara and Vatlayer codes, keep only the Avalara code.
    """

    Product = apps.get_model("product", "Product")
    ProductType = apps.get_model("product", "ProductType")
    TaxClass = apps.get_model("tax", "TaxClass")

    query = Q(metadata__has_key=VATLAYER_CODE_META_KEY) | Q(
        metadata__has_key=AVATAX_CODE_META_KEY
    )

    tax_class_metadata = {}

    product_types = (
        ProductType.objects.filter(query).values("id", "metadata").order_by("pk")
    )
    for batch_pks in query