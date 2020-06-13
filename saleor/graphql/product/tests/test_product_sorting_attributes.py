import os.path
from decimal import Decimal

import graphene
import pytest

from ....attribute import AttributeInputType, AttributeType
from ....attribute import models as attribute_models
from ....attribute.utils import associate_attribute_values_to_instance
from ....product import ProductTypeKind
from ....product import models as product_models
from ...tests.utils import get_graphql_content

HERE = os.path.realpath(os.path.dirname(__file__))

QUERY_SORT_PRODUCTS_BY_ATTRIBUTE = """
query products(
  $field: ProductOrderField
  $attributeId: ID
  $direction: OrderDirection!
  $channel: String
) {
  products(
    first: 100,
    channel: $channel,
    sortBy: { field: $field, attributeId: $attributeId, direction: $direction }
  ) {
    edges {
      node {
        name
        attributes {
          attribute {
            slug
          }
          values {
            name
          }
        }
      }
    }
  }
}
"""

COLORS = (["Blue", "Red"], ["Blue", "Gray"], ["Pink"], ["Pink"], ["Green"])
TRADEMARKS = ("A", "A", "ab", "b", "y")
DUMMIES = ("Oopsie",)


@pytest.fixture
def products_structures(category, channel_USD):
    def attr_value(attribute, *values):
        return [attribute.values.get_or_create(name=v, slug=v)[0] for v in values]

    assert product_models.Product.objects.count() == 0

    in_multivals = AttributeInputType.MULTISELECT

    pt_apples, pt_oranges, pt_other = list(
        product_models.ProductType.objects.bulk_create(
            [
                product_models.ProductType(
                    name="Apples", slug="apples", has_variants=False
                ),
                product_models.ProductType(
                    name="Oranges", slug="oranges", has_variants=False
                ),
                product_models.ProductType(
                    name="Other attributes", slug="other", has_variants=False
                ),
            ]
        )
    )

    colors_attr, trademark_attr, dummy_attr = list(
        attribute_models.Attribute.objects.bulk_create(
            [
                attribute_models.Attribute(
                    name="Colors",
                    slug="colors",
                    input_type=in_multivals,
                    type=AttributeType.PRODUCT_TYPE,
                ),
                attribute_models.Attribute(
                    name="Trademark", slug="trademark", type=AttributeType.PRODUCT_TYPE
                ),
                attribute_models.Attribute(
                    name="Dummy", slug="dummy", type=AttributeType.PRODUCT_TYPE
                ),
            ]
        )
    )

    # Manually add every attribute to given product types
    # to force the preservation of ordering
    pt_apples.product_attributes.add(colors_attr)
    pt_apples.product_attributes.add(trademark_attr)

    pt_oranges.product_attributes.add(colors_attr)
    pt_oranges.product_attributes.add(trademark_attr)

    pt_other.product_attributes.add(dummy_attr)

    assert len(COLORS) == len(TRADEMARKS)

    apples = list(
        product_models.Product.objects.bulk_create(
            [
                product_models.Product(
                    name=f"{attrs[0]} Apple - {attrs[1]} ({i})",
                    slug=f"{attrs[0]}-apple-{attrs[1]}-({i})",
                    product_type=pt_apples,
                    category=category,
                )
                for i, attrs in enumerate(zip(COLORS, TRADEMARKS))
            ]
        )
    )
    for product_apple in apples:
        product_models.ProductChannelListing.objects.create(
            product=product_apple,
            channel=channel_USD,
            is_published=True,
            visible_in_listings=True,
        )
        variant = product_models.ProductVariant.objects.create(
            product=product_apple, sku=product_apple.slug