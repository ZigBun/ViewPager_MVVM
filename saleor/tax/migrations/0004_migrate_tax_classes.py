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
    for batch_pks in queryset_in_batches(product_types):
        tax_classes_from_product_types = defaultdict(list)
        product_types = ProductType.objects.filter(pk__in=batch_pks)
        for product_type in product_types:
            tax_class_name, metadata = _populate_tax_class_name_and_metadata(
                product_type
            )
            if tax_class_name:
                tax_classes_from_product_types[tax_class_name].append(product_type.pk)
                tax_class_metadata[tax_class_name] = metadata

        for name, ids in tax_classes_from_product_types.items():
            tax_class, _ = TaxClass.objects.get_or_create(
                name=name, metadata=tax_class_metadata.get(name, {})
            )
            ProductType.objects.filter(id__in=ids).update(tax_class=tax_class)

    products = Product.objects.filter(query).values("id", "metadata").order_by("pk")
    tax_classes_from_products = defaultdict(list)
    for batch_pks in queryset_in_batches(products):
        products = Product.objects.filter(pk__in=batch_pks)
        for product in products:
            tax_class_name, metadata = _populate_tax_class_name_and_metadata(product)
            if tax_class_name:
                tax_classes_from_products[tax_class_name].append(product.pk)
                tax_class_metadata[tax_class_name] = metadata

        for name, ids in tax_classes_from_products.items():
            tax_class, _ = TaxClass.objects.get_or_create(
                name=name, metadata=tax_class_metadata.get(name, {})
            )
            Product.objects.filter(id__in=ids).update(tax_class=tax_class)


def migrate_products_with_disabled_taxes(apps, _schema_editor):
    Product = apps.get_model("product", "Product")
    TaxClass = apps.get_model("tax", "TaxClass")
    TaxClassCountryRate = apps.get_model("tax", "TaxClassCountryRate")

    zero_rate_tax_class = None
    qs = Product.objects.filter(charge_taxes=False).order_by("pk")
    if qs.exists():
        zero_rate_tax_class, _ = TaxClass.objects.get_or_create(
            name=TAX_CLASS_ZERO_RATE,
            defaults={
                "metadata": {
                    AVATAX_CODE_META_KEY: TAX_CODE_NON_TAXABLE_PRODUCT,
                    AVATAX_DESCRIPTION_META_KEY: "Non-taxable product",
                }
            },
        )

        # Create 0% rates for all countries
        rates = [
            TaxClassCountryRate(tax_class=zero_rate_tax_class, rate=0, country=code)
            for code in countries.countries.keys()
        ]
        TaxClassCountryRate.objects.bulk_create(rates)

    # Assign products with charge_taxes=False to the 0% rate tax class
    if zero_rate_tax_class:
        for batch_pks in queryset_in_batches(qs):
            Product.objects.filter(id__in=batch_pks).update(
                tax_class=zero_rate_tax_class
            )


class Migration(migrations.Migration):
    dependencies = [
        ("tax", "0003_add_manage_taxes_permission"),
        ("product", "0177_product_tax_class_producttype_tax_class"),
    ]

    operations = [
        migrations.RunPython(migrate_product_tax_codes, migrations.RunPython.noop),
        migrations.RunPython(
            migrate_products_with_disabled_taxes, migrations.RunPython.noop
        ),
    ]
