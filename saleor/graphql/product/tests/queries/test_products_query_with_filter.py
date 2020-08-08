from datetime import datetime, timedelta
from decimal import Decimal

import graphene
import pytest
import pytz
from django.utils import timezone

from .....attribute import AttributeInputType, AttributeType
from .....attribute.models import Attribute, AttributeValue
from .....attribute.utils import associate_attribute_values_to_instance
from .....core.postgres import FlatConcatSearchVector
from .....core.units import MeasurementUnits
from .....product import ProductTypeKind
from .....product.models import (
    Category,
    Product,
    ProductChannelListing,
    ProductType,
    ProductVariantChannelListing,
)
from .....product.search import prepare_product_search_vector_value
from .....tests.utils import dummy_editorjs
from .....warehouse.models import Allocation, Reservation, Stock, Warehouse
from ....tests.utils import get_graphql_content


@pytest.fixture
def query_products_with_filter():
    query = """
        query ($filter: ProductFilterInput!, $channel: String) {
          products(first:5, filter: $filter, channel: $channel) {
            edges{
              node{
                id
                name
              }
            }
          }
        }
        """
    return query


def test_products_query_with_filter_attributes(
    query_products_with_filter,
    staff_api_client,
    product,
    permission_manage_products,
    channel_USD,
):
    product_type = ProductType.objects.create(
        name="Custom Type",
        slug="custom-type",
        has_variants=True,
        is_shipping_required=True,
        kind=ProductTypeKind.NORMAL,
    )
    attribute = Attribute.objects.create(slug="new_attr", name="Attr")
    attribute.product_types.add(product_type)
    attr_value = AttributeValue.objects.create(
        attribute=attribute, name="First", slug="first"
    )
    second_product = product
    second_product.id = None
    second_product.product_type = product_type
    second_product.slug = "second-product"
    second_product.save()
    associate_attribute_values_to_instance(second_product, attribute, attr_value)

    variables = {
        "filter": {
            "attributes": [{"slug": attribute.slug, "values": [attr_value.slug]}],
        },
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    second_product_id = graphene.Node.to_global_id("Product", second_product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == second_product_id
    assert products[0]["node"]["name"] == second_product.name


@pytest.mark.parametrize(
    "gte, lte, expected_products_index",
    [
        (None, 8, [1, 2]),
        (0, 8, [1, 2]),
        (7, 8, []),
        (5, None, [0, 1, 2]),
        (8, 10, [0]),
        (12, None, [0]),
        (20, None, []),
        (20, 8, []),
        (5, 5, [1, 2]),
    ],
)
def test_products_query_with_filter_numeric_attributes(
    gte,
    lte,
    expected_products_index,
    query_products_with_filter,
    staff_api_client,
    product,
    category,
    numeric_attribute,
    permission_manage_products,
):
    product.product_type.product_attributes.add(numeric_attribute)
    associate_attribute_values_to_instance(
        product, numeric_attribute, *numeric_attribute.values.all()
    )

    product_type = ProductType.objects.create(
        name="Custom Type",
        slug="custom-type",
        kind=ProductTypeKind.NORMAL,
        has_variants=True,
        is_shipping_required=True,
    )
    numeric_attribute.product_types.add(product_type)

    second_product = Product.objects.create(
        name="Second product",
        slug="second-product",
        product_type=product_type,
        category=category,
    )
    attr_value = AttributeValue.objects.create(
        attribute=numeric_attribute, name="5", slug="5"
    )

    associate_attribute_values_to_instance(
        second_product, numeric_attribute, attr_value
    )

    third_product = Product.objects.create(
        name="Third product",
        slug="third-product",
        product_type=product_type,
        category=category,
    )
    attr_value = AttributeValue.objects.create(
        attribute=numeric_attribute, name="5", slug="5_X"
    )

    associate_attribute_values_to_instance(third_product, numeric_attribute, attr_value)

    second_product.refresh_from_db()
    third_product.refresh_from_db()
    products_instances = [product, second_product, third_product]
    products_ids = [
        graphene.Node.to_global_id("Product", p.pk) for p in products_instances
    ]
    values_range = {}
    if gte:
        values_range["gte"] = gte
    if lte:
        values_range["lte"] = lte
    variables = {
        "filter": {
            "attributes": [
                {"slug": numeric_attribute.slug, "valuesRange": values_range}
            ]
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]

    assert len(products) == len(expected_products_index)
    assert set(product["node"]["id"] for product in products) == {
        products_ids[index] for index in expected_products_index
    }
    assert set(product["node"]["name"] for product in products) == {
        products_instances[index].name for index in expected_products_index
    }


@pytest.mark.parametrize(
    "filter_value, expected_products_index",
    [
        (False, [0, 1]),
        (True, [0]),
    ],
)
def test_products_query_with_filter_boolean_attributes(
    filter_value,
    expected_products_index,
    query_products_with_filter,
    staff_api_client,
    product,
    category,
    boolean_attribute,
    permission_manage_products,
):
    product.product_type.product_attributes.add(boolean_attribute)

    associate_attribute_values_to_instance(
        product, boolean_attribute, boolean_attribute.values.get(boolean=filter_value)
    )

    product_type = ProductType.objects.create(
        name="Custom Type",
        slug="custom-type",
        kind=ProductTypeKind.NORMAL,
        has_variants=True,
        is_shipping_required=True,
    )
    boolean_attribute.product_types.add(product_type)

    second_product = Product.objects.create(
        name="Second product",
        slug="second-product",
        product_type=product_type,
        category=category,
    )
    associate_attribute_values_to_instance(
        second_product, boolean_attribute, boolean_attribute.values.get(boolean=False)
    )

    second_product.refresh_from_db()
    products_instances = [product, second_product]
    products_ids = [
        graphene.Node.to_global_id("Product", p.pk) for p in products_instances
    ]

    variables = {
        "filter": {
            "attributes": [{"slug": boolean_attribute.slug, "boolean": filter_value}]
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]

    assert len(products) == len(expected_products_index)
    assert set(product["node"]["id"] for product in products) == {
        products_ids[index] for index in expected_products_index
    }
    assert set(product["node"]["name"] for product in products) == {
        products_instances[index].name for index in expected_products_index
    }


def test_products_query_with_filter_by_attributes_values_and_range(
    query_products_with_filter,
    staff_api_client,
    product,
    category,
    numeric_attribute,
    permission_manage_products,
):
    product_attr = product.attributes.first()
    attr_value_1 = product_attr.values.first()
    product.product_type.product_attributes.add(numeric_attribute)
    associate_attribute_values_to_instance(
        product, numeric_attribute, *numeric_att