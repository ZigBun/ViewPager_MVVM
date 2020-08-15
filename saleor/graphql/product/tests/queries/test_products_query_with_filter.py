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
    attr_value_2 = AttributeValue.objects.create(
        attribute=numeric_attribute, name="5.2", slug="5_2"
    )

    associate_attribute_values_to_instance(
        second_product, numeric_attribute, attr_value_2
    )

    second_product.refresh_from_db()

    variables = {
        "filter": {
            "attributes": [
                {"slug": numeric_attribute.slug, "valuesRange": {"gte": 2}},
                {"slug": attr_value_1.attribute.slug, "values": [attr_value_1.slug]},
            ]
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == graphene.Node.to_global_id(
        "Product", product.pk
    )
    assert products[0]["node"]["name"] == product.name


def test_products_query_with_filter_swatch_attributes(
    query_products_with_filter,
    staff_api_client,
    product,
    category,
    swatch_attribute,
    permission_manage_products,
):
    product.product_type.product_attributes.add(swatch_attribute)
    associate_attribute_values_to_instance(
        product, swatch_attribute, *swatch_attribute.values.all()
    )

    product_type = ProductType.objects.create(
        name="Custom Type",
        slug="custom-type",
        has_variants=True,
        is_shipping_required=True,
    )
    swatch_attribute.product_types.add(product_type)

    second_product = Product.objects.create(
        name="Second product",
        slug="second-product",
        product_type=product_type,
        category=category,
    )
    attr_value = AttributeValue.objects.create(
        attribute=swatch_attribute, name="Dark", slug="dark"
    )

    associate_attribute_values_to_instance(second_product, swatch_attribute, attr_value)

    second_product.refresh_from_db()

    variables = {
        "filter": {
            "attributes": [
                {"slug": swatch_attribute.slug, "values": [attr_value.slug]},
            ]
        }
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    second_product_id = graphene.Node.to_global_id("Product", second_product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == second_product_id
    assert products[0]["node"]["name"] == second_product.name


def test_products_query_with_filter_date_range_date_attributes(
    query_products_with_filter,
    staff_api_client,
    product_list,
    permission_manage_products,
    date_attribute,
    channel_USD,
):
    """Ensure both products will be returned when filtering attributes by date range,
    products with the same date attribute value."""

    # given
    product_type = product_list[0].product_type
    date_value = timezone.now()
    product_type.product_attributes.add(date_attribute)
    attr_value_1 = AttributeValue.objects.create(
        attribute=date_attribute, name="First", slug="first", date_time=date_value
    )
    attr_value_2 = AttributeValue.objects.create(
        attribute=date_attribute, name="Second", slug="second", date_time=date_value
    )
    attr_value_3 = AttributeValue.objects.create(
        attribute=date_attribute,
        name="Third",
        slug="third",
        date_time=date_value - timedelta(days=1),
    )

    associate_attribute_values_to_instance(
        product_list[0], date_attribute, attr_value_1
    )
    associate_attribute_values_to_instance(
        product_list[1], date_attribute, attr_value_2
    )
    associate_attribute_values_to_instance(
        product_list[2], date_attribute, attr_value_3
    )

    variables = {
        "filter": {
            "attributes": [
                {
                    "slug": date_attribute.slug,
                    "date": {"gte": date_value.date(), "lte": date_value.date()},
                }
            ],
        },
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)

    # when
    response = staff_api_client.post_graphql(query_products_with_filter, variables)

    # then
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]
    assert len(products) == 2
    assert {node["node"]["id"] for node in products} == {
        graphene.Node.to_global_id("Product", instance.id)
        for instance in product_list[:2]
    }


def test_products_query_with_filter_date_range_date_variant_attributes(
    query_products_with_filter,
    staff_api_client,
    product_list,
    permission_manage_products,
    date_attribute,
    channel_USD,
):
    """Ensure both products will be returned when filtering attributes by date range,
    variants with the same date attribute value."""

    # given
    product_type = product_list[0].product_type
    date_value = timezone.now()
    product_type.variant_attributes.add(date_attribute)
    attr_value_1 = AttributeValue.objects.create(
        attribute=date_attribute,
        name="First",
        slug="first",
        date_time=date_value - timedelta(days=1),
    )
    attr_value_2 = AttributeValue.objects.create(
        attribute=date_attribute, name="Second", slug="second", date_time=date_value
    )
    attr_value_3 = AttributeValue.objects.create(
        attribute=date_attribute, name="Third", slug="third", date_time=date_value
    )

    associate_attribute_values_to_instance(
        product_list[0].variants.first(), date_attribute, attr_value_1
    )
    associate_attribute_values_to_instance(
        product_list[1].variants.first(), date_attribute, attr_value_2
    )
    associate_attribute_values_to_instance(
        product_list[2].variants.first(), date_attribute, attr_value_3
    )

    variables = {
        "filter": {
            "attributes": [
                {
                    "slug": date_attribute.slug,
                    "date": {"gte": date_value.date(), "lte": date_value.date()},
                }
            ],
        },
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)

    # when
    response = staff_api_client.post_graphql(query_products_with_filter, variables)

    # then
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]
    assert len(products) == 2
    assert {node["node"]["id"] for node in products} == {
        graphene.Node.to_global_id("Product", instance.id)
        for instance in product_list[1:]
    }


def test_products_query_with_filter_date_range_date_time_attributes(
    query_products_with_filter,
    staff_api_client,
    product_list,
    permission_manage_products,
    date_time_attribute,
    channel_USD,
):
    """Ensure both products will be returned when filtering attributes by date time
    range, products with the same date time attribute value."""

    # given
    product_type = product_list[0].product_type
    date_value = timezone.now()
    product_type.product_attributes.add(date_time_attribute)
    attr_value_1 = AttributeValue.objects.create(
        attribute=date_time_attribute, name="First", slug="first", date_time=date_value
    )
    attr_value_2 = AttributeValue.objects.create(
        attribute=date_time_attribute,
        name="Second",
        slug="second",
        date_time=date_value,
    )
    attr_value_3 = AttributeValue.objects.create(
        attribute=date_time_attribute,
        name="Third",
        slug="third",
        date_time=date_value - timedelta(days=1),
    )

    associate_attribute_values_to_instance(
        product_list[0], date_time_attribute, attr_value_1
    )
    associate_attribute_values_to_instance(
        product_list[1], date_time_attribute, attr_value_2
    )
    associate_attribute_values_to_instance(
        product_list[2], date_time_attribute, attr_value_3
    )

    variables = {
        "filter": {
            "attributes": [
                {
                    "slug": date_time_attribute.slug,
                    "date": {"gte": date_value.date(), "lte": date_value.date()},
                }
            ],
        },
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)

    # when
    response = staff_api_client.post_graphql(query_products_with_filter, variables)

    # then
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]
    assert len(products) == 2
    assert {node["node"]["id"] for node in products} == {
        graphene.Node.to_global_id("Product", instance.id)
        for instance in product_list[:2]
    }


def test_products_query_with_filter_date_range_date_time_variant_attributes(
    query_products_with_filter,
    staff_api_client,
    product_list,
    permission_manage_products,
    date_time_attribute,
    channel_USD,
):
    """Ensure both products will be returned when filtering attributes by date time
    range, variant and product with the same date time attribute value."""

    # given
    product_type = product_list[0].product_type
    date_value = timezone.now()
    product_type.variant_attributes.add(date_time_attribute)
    attr_value_1 = AttributeValue.objects.create(
        attribute=date_time_attribute,
        name="First",
        slug="first",
        date_time=date_value - timedelta(days=1),
    )
    attr_value_2 = AttributeValue.objects.create(
        attribute=date_time_attribute,
        name="Second",
        slug="second",
        date_time=date_value,
    )
    attr_value_3 = AttributeValue.objects.create(
        attribute=date_time_attribute, name="Third", slug="third", date_time=date_value
    )

    associate_attribute_values_to_instance(
        product_list[0].variants.first(), date_time_attribute, attr_value_1
    )
    associate_attribute_values_to_instance(
        product_list[1].variants.first(), date_time_attribute, attr_value_2
    )
    associate_attribute_values_to_instance(
        product_list[2].variants.first(), date_time_attribute, attr_value_3
    )

    variables = {
        "filter": {
            "attributes": [
                {
                    "slug": date_time_attribute.slug,
                    "date": {"gte": date_value.date(), "lte": date_value.date()},
                }
            ],
        },
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)

    # when
    response = staff_api_client.post_graphql(query_products_with_filter, variables)

    # then
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]
    assert len(products) == 2
    assert {node["node"]["id"] for node in products} == {
        graphene.Node.to_global_id("Product", instance.id)
        for instance in product_list[1:]
    }


def test_products_query_with_filter_date_time_range_date_time_attributes(
    query_products_with_filter,
    staff_api_client,
    product_list,
    permission_manage_products,
    date_time_attribute,
    channel_USD,
):
    """Ensure both products will be returned when filtering by attributes by date range
    variants with the same date attribute value."""

    # given
    product_type = product_list[0].product_type
    date_value = datetime.now(tz=pytz.utc)
    product_type.product_attributes.add(date_time_attribute)
    product_type.variant_attributes.add(date_time_attribute)
    attr_value_1 = AttributeValue.objects.create(
        attribute=date_time_attribute,
        name="First",
        slug="first",
        date_time=date_value - timedelta(hours=2),
    )
    attr_value_2 = AttributeValue.objects.create(
        attribute=date_time_attribute,
        name="Second",
        slug="second",
        date_time=date_value + timedelta(hours=3),
    )
    attr_value_3 = AttributeValue.objects.create(
        attribute=date_time_attribute,
        name="Third",
        slug="third",
        date_time=date_value - timedelta(hours=6),
    )

    associate_attribute_values_to_instance(
        product_list[0], date_time_attribute, attr_value_1
    )
    associate_attribute_values_to_instance(
        product_list[1].variants.first(), date_time_attribute, attr_value_2
    )
    associate_attribute_values_to_instance(
        product_list[2].variants.first(), date_time_attribute, attr_value_3
    )

    variables = {
        "filter": {
            "attributes": [
                {
                    "slug": date_time_attribute.slug,
                    "dateTime": {
                        "gte": date_value - timedelta(hours=4),
                        "lte": date_value + timedelta(hours=4),
                    },
                }
            ],
        },
    }

    staff_api_client.user.user_permissions.add(permission_manage_products)

    # when
    response = staff_api_client.post_graphql(query_products_with_filter, variables)

    # then
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]
    assert len(products) == 2
    assert {node["node"]["id"] for node in products} == {
        graphene.Node.to_global_id("Product", instance.id)
        for instance in product_list[:2]
    }


def test_products_query_filter_by_non_existing_attribute(
    query_products_with_filter, api_client, product_list, channel_USD
):
    variables = {
        "channel": channel_USD.slug,
        "filter": {"attributes": [{"slug": "i-do-not-exist", "values": ["red"]}]},
    }
    response = api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]
    assert len(products) == 0


def test_products_query_with_filter_category(
    query_products_with_filter, staff_api_client, product, permission_manage_products
):
    category = Category.objects.create(name="Custom", slug="custom")
    second_product = product
    second_product.id = None
    second_product.slug = "second-product"
    second_product.category = category
    second_product.save()

    category_id = graphene.Node.to_global_id("Category", category.id)
    variables = {"filter": {"categories": [category_id]}}
    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    second_product_id = graphene.Node.to_global_id("Product", second_product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == second_product_id
    assert products[0]["node"]["name"] == second_product.name


def test_products_query_with_filter_has_category_false(
    query_products_with_filter, staff_api_client, product, permission_manage_products
):
    second_product = product
    second_product.category = None
    second_product.id = None
    second_product.slug = "second-product"
    second_product.save()

    variables = {"filter": {"hasCategory": False}}
    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    second_product_id = graphene.Node.to_global_id("Product", second_product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == second_product_id
    assert products[0]["node"]["name"] == second_product.name


def test_products_query_with_filter_has_category_true(
    query_products_with_filter,
    staff_api_client,
    product_without_category,
    permission_manage_products,
):
    category = Category.objects.create(name="Custom", slug="custom")
    second_product = product_without_category
    second_product.category = category
    second_product.id = None
    second_product.slug = "second-product"
    second_product.save()

    variables = {"filter": {"hasCategory": True}}
    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    second_product_id = graphene.Node.to_global_id("Product", second_product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == second_product_id
    assert products[0]["node"]["name"] == second_product.name


def test_products_query_with_filter_collection(
    query_products_with_filter,
    staff_api_client,
    product,
    collection,
    permission_manage_products,
):
    second_product = product
    second_product.id = None
    second_product.slug = "second-product"
    second_product.save()
    second_product.collections.add(collection)

    collection_id = graphene.Node.to_global_id("Collection", collection.id)
    variables = {"filter": {"collections": [collection_id]}}
    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    second_product_id = graphene.Node.to_global_id("Product", second_product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == second_product_id
    assert products[0]["node"]["name"] == second_product.name


def test_products_query_with_filter_category_and_search(
    query_products_with_filter,
    staff_api_client,
    product,
    permission_manage_products,
):
    category = Category.objects.create(name="Custom", slug="custom")
    second_product = product
    second_product.id = None
    second_product.slug = "second-product"
    second_product.category = category
    product.category = category
    second_product.save()
    product.save()

    for pr in [product, second_product]:
        pr.search_vector = FlatConcatSearchVector(
            *prepare_product_search_vector_value(pr)
        )
    Product.objects.bulk_update([product, second_product], ["search_vector"])

    category_id = graphene.Node.to_global_id("Category", category.id)
    variables = {"filter": {"categories": [category_id], "search": product.name}}
    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    product_id = graphene.Node.to_global_id("Product", product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == product_id
    assert products[0]["node"]["name"] == product.name


def test_products_query_with_filter_gift_card_false(
    query_products_with_filter,
    staff_api_client,
    product,
    shippable_gift_card_product,
    permission_manage_products,
):
    # given
    variables = {"filter": {"giftCard": False}}
    staff_api_client.user.user_permissions.add(permission_manage_products)

    # when
    response = staff_api_client.post_graphql(query_products_with_filter, variables)

    # then
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == graphene.Node.to_global_id(
        "Product", product.pk
    )


def test_products_query_with_filter_gift_card_true(
    query_products_with_filter,
    staff_api_client,
    product,
    shippable_gift_card_product,
    permission_manage_products,
):
    # given
    variables = {"filter": {"giftCard": True}}
    staff_api_client.user.user_permissions.add(permission_manage_products)

    # when
    response = staff_api_client.post_graphql(query_products_with_filter, variables)

    # then
    content = get_graphql_content(response)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == graphene.Node.to_global_id(
        "Product", shippable_gift_card_product.pk
    )


@pytest.mark.parametrize(
    "products_filter",
    [
        {"minimalPrice": {"gte": 1.0, "lte": 2.0}},
        {"isPublished": False},
        {"search": "Juice1"},
    ],
)
def test_products_query_with_filter(
    products_filter,
    query_products_with_filter,
    staff_api_client,
    product,
    permission_manage_products,
    channel_USD,
):
    assert "Juice1" not in product.name

    second_product = product
    second_product.id = None
    second_product.name = "Apple Juice1"
    second_product.slug = "apple-juice1"
    second_product.save()
    variant_second_product = second_product.variants.create(
        product=second_product,
        sku=second_product.slug,
    )
    ProductVariantChannelListing.objects.create(
        variant=variant_second_product,
        channel=channel_USD,
        price_amount=Decimal(1.99),
        cost_price_amount=Decimal(1),
        currency=channel_USD.currency_code,
    )
    ProductChannelListing.objects.create(
        product=second_product,
        discounted_price_amount=Decimal(1.99),
        channel=channel_USD,
        is_published=False,
    )
    second_product.search_vector = FlatConcatSearchVector(
        *prepare_product_search_vector_value(second_product)
    )
    second_product.save(update_fields=["search_vector"])
    variables = {"filter": products_filter, "channel": channel_USD.slug}
    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_products_with_filter, variables)
    content = get_graphql_content(response)
    second_product_id = graphene.Node.to_global_id("Product", second_product.id)
    products = content["data"]["products"]["edges"]

    assert len(products) == 1
    assert products[0]["node"]["id"] == second_product_id
    assert products[0]["node"]["name"] == second_product.name


def test_products_query_with_price_filter_as_staff(
    query_products_with_filter,
    staff_api_client,
    product_list,
    permission_manage_products,
    channel_USD,
):
    product = product_list[0]
    product.variants.first().channel_listings.filter().update(price_amount=None)

    variables = {
        "filter": {"price": {"gte": 9, "lte": 31}},
        "channel": channel_USD.slug,
    }
    staff_api_client.user.user_permissions.add(permission_manage_products)
    response = staff_api_client.post_graphql(query_