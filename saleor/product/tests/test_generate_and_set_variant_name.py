from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest

from ...attribute import AttributeInputType
from ...attribute.models import AttributeValue
from ...attribute.utils import associate_attribute_values_to_instance
from ...product import ProductTypeKind
from ...product.models import ProductVariantChannelListing
from ..models import Product, ProductType, ProductVariant
from ..tasks import _update_variants_names
from ..utils.variants import generate_and_set_variant_name


@pytest.fixture()
def variant_with_no_attributes(category, channel_USD):
    """Create a variant having no attributes, the same for the parent product."""
    product_type = ProductType.objects.create(
        name="Test product type",
        has_variants=True,
        is_shipping_required=True,
        kind=ProductTypeKind.NORMAL,
    )
    product = Product.objects.create(
        name="Test product",
        product_type=product_type,
        category=category,
    )
    variant = ProductVariant.objects.create(product=product, sku="123")
    ProductVariantChannelListing.objects.create(
        variant=variant,
        channel=channel_USD,
        cost_price_amount=Decimal(1),
        price_amount=Decimal(10),
        currency=channel_USD.currency_code,
    )
    return variant


def test_generate_and_set_variant_name_different_attributes(
    variant_with_no_attributes, color_attribute_without_values, size_attribute
):
    """Test the name generation from a given variant containing multiple attributes and
    different input types (dropdown and multiselect).
    """

    variant = variant_with_no_attributes
    color_attribute = color_attribute_without_values

    # Assign the attributes to the product type
    variant.product.product_type.variant_attributes.add(
        size_attribute, through_defaults={"variant_selection": True}
    )
    variant.product.product_type.variant_attributes.add(color_attribute)

    # Set the color attribute to a multi-value attribute
    color_attribute.input_type = AttributeInputType.MULTISELECT
    color_attribute.save(update_fields=["input_type"])

    # Create colors
    colors = AttributeValue.objects.bulk_create(
        [
            AttributeValue(attribute=color_attribute, name="Yellow", slug="yellow"),
            AttributeValue(attribute=color_attribute, name="Blue", slug="blue"),
            AttributeValue(attribute=color_attribute, name="Red", slug="red"),
        ]
    )

    # Retrieve the size attribute value "Big"
    size = size_attribute.values.get(slug="big")

    # Associate the colors and size to variant attributes
    associate_attribute_values_to_instance(variant, color_attribute, *tuple(colors))
    associate_attribute_values_to_instance(variant, size_attribute, size)

    # Generate the variant name from the attributes
    generate_and_set_variant_name(variant, variant.sku)
    variant.refresh_from_db()
    assert variant.name == "Big"


def test_generate_and_set_variant_name_only_variant_selection_attributes(
    variant_with_no_attributes, color_attribute_without_values, size_attribute
):
    """Test the name generation for a given variant containing multiple attributes
    with input types allowed in variant selection.
    """

    variant = variant_with_no_attributes
    color_attribute = color_attribute_without_values

    # Assign the attributes to the product type
    variant.product.product_type.variant_attributes.set(
        (color_attribute, size_attribute), through_defaults={"variant_selection": True}
    )

    # Create values
    colors = AttributeValue.objects.bulk_create(
        [
            AttributeValue(
                attribute=color_attribute, name="Yellow", slug="yellow", sort_order=1
            ),
            AttributeValue(
                attribute=color_attribute, name="Blue", slug="blue", sort_order=2
            ),
            AttributeValue(
                attribute=color_attribute, name="Red", slug="red", sort_order=3
            ),
        ]
    )

    # Retrieve the size attribute value "Big"
    size = size_attribute.values.get(slug="big")
    size.sort_order = 4
    size.save(update_fields=["sort_order"])

    # Associate the colors and size to variant attributes
    associate_attribute_values_to_instance(variant, color_attribute, *tuple(colors))
    associate_attribute_values_to_instance(variant, size_attribute, size)

    # Generate the variant name from the attributes
    generate_and_set_variant_name(variant, variant.sku)
    variant.refresh_from_db()
    assert variant.name == "Big / Yellow, Blue, Red"


def test_generate_and_set_variant_name_only_not_variant_selection_attributes(
    variant_with_no_attributes, color_attribute_without_values, file_attribute
):
    """Test the name generation for a given variant containing multiple attributes
    with input types not allowed in variant selection.
    """

    variant = variant_with_no_attributes
    color_attribute = color_attribute_without_values

    # Assign the attributes to th