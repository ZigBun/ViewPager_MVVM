import json
from datetime import datetime, timedelta
from unittest.mock import ANY, patch
from uuid import uuid4

import graphene
import pytz
from django.conf import settings
from django.utils.text import slugify
from freezegun import freeze_time

from .....product.error_codes import ProductErrorCode
from .....tests.utils import dummy_editorjs, flush_post_commit_hooks
from ....core.enums import WeightUnitsEnum
from ....tests.utils import get_graphql_content

CREATE_VARIANT_MUTATION = """
      mutation createVariant ($input: ProductVariantCreateInput!) {
                productVariantCreate(input: $input) {
                    errors {
                      field
                      message
                      attributes
                      code
                    }
                    productVariant {
                        id
                        name
                        sku
                        attributes {
                            attribute {
                                slug
                            }
                            values {
                                name
                                slug
                                reference
                                richText
                                plainText
                                boolean
                                date
                                dateTime
                                file {
                                    url
                                    contentType
                                }
                            }
                        }
                        weight {
                            value
                            unit
                        }
                        stocks {
                            quantity
                            warehouse {
                                slug
                            }
                        }
                        preorder {
                            globalThreshold
                            endDate
                        }
                        metadata {
                            key
                            value
                        }
                        privateMetadata {
                            key
                            value
                        }
                        externalReference
                    }
                }
            }

"""


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
@patch("saleor.plugins.manager.PluginsManager.product_variant_updated")
def test_create_variant_with_name(
    updated_webhook_mock,
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    permission_manage_products,
    warehouse,
):
    # given
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"
    name = "test-name"
    weight = 10.22
    metadata_key = "md key"
    metadata_value = "md value"
    variant_slug = product_type.variant_attributes.first().slug
    attribute_id = graphene.Node.to_global_id(
        "Attribute", product_type.variant_attributes.first().pk
    )
    variant_value = "test-value"
    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]
    external_reference = "test-ext-ref"

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "name": name,
            "weight": weight,
            "attributes": [{"id": attribute_id, "values": [variant_value]}],
            "trackInventory": True,
            "metadata": [{"key": metadata_key, "value": metadata_value}],
            "privateMetadata": [{"key": metadata_key, "value": metadata_value}],
            "externalReference": external_reference,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        CREATE_VARIANT_MUTATION, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    # then
    assert not content["errors"]
    data = content["productVariant"]
    assert data["name"] == name
    assert data["sku"] == sku
    assert data["attributes"][0]["attribute"]["slug"] == variant_slug
    assert data["attributes"][0]["values"][0]["slug"] == variant_value
    assert data["weight"]["unit"] == WeightUnitsEnum.KG.name
    assert data["weight"]["value"] == weight
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug
    assert data["metadata"][0]["key"] == metadata_key
    assert data["metadata"][0]["value"] == metadata_value
    assert data["privateMetadata"][0]["key"] == metadata_key
    assert data["privateMetadata"][0]["value"] == metadata_value
    assert data["externalReference"] == external_reference

    created_webhook_mock.assert_called_once_with(product.variants.last())
    updated_webhook_mock.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
@patch("saleor.plugins.manager.PluginsManager.product_variant_updated")
def test_create_variant_without_name(
    updated_webhook_mock,
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    permission_manage_products,
    warehouse,
):
    # given
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"
    weight = 10.22
    variant_slug = product_type.variant_attributes.first().slug
    attribute_id = graphene.Node.to_global_id(
        "Attribute", product_type.variant_attributes.first().pk
    )
    variant_value = "test-value"
    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "weight": weight,
            "attributes": [{"id": attribute_id, "values": [variant_value]}],
            "trackInventory": True,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    # then
    assert not content["errors"]
    data = content["productVariant"]
    assert data["name"] == variant_value
    assert data["sku"] == sku
    assert data["attributes"][0]["attribute"]["slug"] == variant_slug
    assert data["attributes"][0]["values"][0]["slug"] == variant_value
    assert data["weight"]["unit"] == WeightUnitsEnum.KG.name
    assert data["weight"]["value"] == weight
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug
    created_webhook_mock.assert_called_once_with(product.variants.last())
    updated_webhook_mock.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
@patch("saleor.plugins.manager.PluginsManager.product_variant_updated")
def test_create_variant_preorder(
    updated_webhook_mock,
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    permission_manage_products,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    attribute_id = graphene.Node.to_global_id(
        "Attribute", product_type.variant_attributes.first().pk
    )
    variant_value = "test-value"
    global_threshold = 10
    end_date = (
        (datetime.now() + timedelta(days=3))
        .astimezone()
        .replace(microsecond=0)
        .isoformat()
    )

    variables = {
        "input": {
            "product": product_id,
            "sku": "1",
            "weight": 10.22,
            "attributes": [{"id": attribute_id, "values": [variant_value]}],
            "preorder": {
                "globalThreshold": global_threshold,
                "endDate": end_date,
            },
        }
    }

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    assert not content["errors"]
    data = content["productVariant"]
    assert data["name"] == variant_value

    assert data["preorder"]["globalThreshold"] == global_threshold
    assert data["preorder"]["endDate"] == end_date
    created_webhook_mock.assert_called_once_with(product.variants.last())
    updated_webhook_mock.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
@patch("saleor.plugins.manager.PluginsManager.product_variant_updated")
def test_create_variant_no_required_attributes(
    updated_webhook_mock,
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    permission_manage_products,
    warehouse,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"
    weight = 10.22

    attribute = product_type.variant_attributes.first()
    attribute.value_required = False
    attribute.save(update_fields=["value_required"])

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "weight": weight,
            "attributes": [],
            "trackInventory": True,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    assert not content["errors"]
    data = content["productVariant"]
    assert data["name"] == sku
    assert data["sku"] == sku
    assert not data["attributes"][0]["values"]
    assert data["weight"]["unit"] == WeightUnitsEnum.KG.name
    assert data["weight"]["value"] == weight
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug
    created_webhook_mock.assert_called_once_with(product.variants.last())
    updated_webhook_mock.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_file_attribute(
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    file_attribute,
    permission_manage_products,
    warehouse,
    site_settings,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"
    weight = 10.22

    product_type.variant_attributes.clear()
    product_type.variant_attributes.add(file_attribute)
    file_attr_id = graphene.Node.to_global_id("Attribute", file_attribute.id)
    existing_value = file_attribute.values.first()
    domain = site_settings.site.domain
    file_url = f"http://{domain}{settings.MEDIA_URL}{existing_value.file_url}"

    values_count = file_attribute.values.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "weight": weight,
            "attributes": [{"id": file_attr_id, "file": file_url}],
            "trackInventory": True,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    assert not content["errors"]
    data = content["productVariant"]
    assert data["name"] == sku
    assert data["sku"] == sku
    assert data["attributes"][0]["attribute"]["slug"] == file_attribute.slug
    assert data["attributes"][0]["values"][0]["slug"] == f"{existing_value.slug}-2"
    assert data["attributes"][0]["values"][0]["name"] == existing_value.name
    assert data["weight"]["unit"] == WeightUnitsEnum.KG.name
    assert data["weight"]["value"] == weight
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug

    file_attribute.refresh_from_db()
    assert file_attribute.values.count() == values_count + 1

    created_webhook_mock.assert_called_once_with(product.variants.last())


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_boolean_attribute(
    created_webhook_mock,
    permission_manage_products,
    product,
    product_type,
    staff_api_client,
    boolean_attribute,
    size_attribute,
    warehouse,
):
    product_type.variant_attributes.add(
        boolean_attribute, through_defaults={"variant_selection": True}
    )
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    boolean_attr_id = graphene.Node.to_global_id("Attribute", boolean_attribute.id)
    size_attr_id = graphene.Node.to_global_id("Attribute", size_attribute.pk)

    variables = {
        "input": {
            "product": product_id,
            "sku": "1",
            "stocks": [
                {
                    "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
                    "quantity": 20,
                }
            ],
            "weight": 10.22,
            "attributes": [
                {"id": boolean_attr_id, "boolean": True},
                {"id": size_attr_id, "values": ["XXXL"]},
            ],
            "trackInventory": True,
        }
    }

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()
    data = content["productVariant"]

    assert not content["errors"]
    assert data["name"] == "Boolean: Yes / XXXL"
    expected_attribute_data = {
        "attribute": {"slug": "boolean"},
        "values": [
            {
                "name": "Boolean: Yes",
                "slug": f"{boolean_attribute.id}_true",
                "reference": None,
                "richText": None,
                "plainText": None,
                "boolean": True,
                "file": None,
                "dateTime": None,
                "date": None,
            }
        ],
    }

    assert expected_attribute_data in data["attributes"]
    created_webhook_mock.assert_called_once_with(product.variants.last())


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_file_attribute_new_value(
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    file_attribute,
    permission_manage_products,
    warehouse,
    site_settings,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"
    weight = 10.22

    product_type.variant_attributes.clear()
    product_type.variant_attributes.add(file_attribute)
    file_attr_id = graphene.Node.to_global_id("Attribute", file_attribute.id)
    new_value = "new_value.txt"
    file_url = f"http://{site_settings.site.domain}{settings.MEDIA_URL}{new_value}"

    values_count = file_attribute.values.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "weight": weight,
            "attributes": [{"id": file_attr_id, "file": file_url}],
            "trackInventory": True,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    assert not content["errors"]
    data = content["productVariant"]
    assert data["name"] == sku
    assert data["sku"] == sku
    assert data["attributes"][0]["attribute"]["slug"] == file_attribute.slug
    assert data["attributes"][0]["values"][0]["slug"] == slugify(new_value)
    assert data["weight"]["unit"] == WeightUnitsEnum.KG.name
    assert data["weight"]["value"] == weight
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug

    file_attribute.refresh_from_db()
    assert file_attribute.values.count() == values_count + 1

    created_webhook_mock.assert_called_once_with(product.variants.last())


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_file_attribute_no_file_url_given(
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    file_attribute,
    permission_manage_products,
    warehouse,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"
    weight = 10.22

    product_type.variant_attributes.clear()
    product_type.variant_attributes.add(file_attribute)
    file_attr_id = graphene.Node.to_global_id("Attribute", file_attribute.id)

    values_count = file_attribute.values.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "weight": weight,
            "attributes": [{"id": file_attr_id}],
            "trackInventory": True,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    errors = content["errors"]
    data = content["productVariant"]
    assert not errors
    assert data["name"] == sku
    assert data["sku"] == sku
    assert data["attributes"][0]["attribute"]["slug"] == file_attribute.slug
    assert len(data["attributes"][0]["values"]) == 0
    assert data["weight"]["unit"] == WeightUnitsEnum.KG.name
    assert data["weight"]["value"] == weight
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug

    file_attribute.refresh_from_db()
    assert file_attribute.values.count() == values_count

    created_webhook_mock.assert_called_once_with(product.variants.last())


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_page_reference_attribute(
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    product_type_page_reference_attribute,
    page_list,
    permission_manage_products,
    warehouse,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"

    product_type.variant_attributes.clear()
    product_type.variant_attributes.add(product_type_page_reference_attribute)
    ref_attr_id = graphene.Node.to_global_id(
        "Attribute", product_type_page_reference_attribute.id
    )

    page_ref_1 = graphene.Node.to_global_id("Page", page_list[0].pk)
    page_ref_2 = graphene.Node.to_global_id("Page", page_list[1].pk)

    values_count = product_type_page_reference_attribute.values.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "attributes": [{"id": ref_attr_id, "references": [page_ref_1, page_ref_2]}],
            "trackInventory": True,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    assert not content["errors"]
    data = content["productVariant"]
    assert data["sku"] == sku
    variant_id = data["id"]
    _, variant_pk = graphene.Node.from_global_id(variant_id)
    assert (
        data["attributes"][0]["attribute"]["slug"]
        == product_type_page_reference_attribute.slug
    )
    expected_values = [
        {
            "slug": f"{variant_pk}_{page_list[0].pk}",
            "file": None,
            "richText": None,
            "plainText": None,
            "reference": page_ref_1,
            "name": page_list[0].title,
            "boolean": None,
            "date": None,
            "dateTime": None,
        },
        {
            "slug": f"{variant_pk}_{page_list[1].pk}",
            "file": None,
            "richText": None,
            "plainText": None,
            "reference": page_ref_2,
            "name": page_list[1].title,
            "boolean": None,
            "date": None,
            "dateTime": None,
        },
    ]
    for value in expected_values:
        assert value in data["attributes"][0]["values"]
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug

    product_type_page_reference_attribute.refresh_from_db()
    assert product_type_page_reference_attribute.values.count() == values_count + 2

    created_webhook_mock.assert_called_once_with(product.variants.last())


@patch("saleor.plugins.manager.PluginsManager.product_variant_updated")
@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_page_reference_attribute_no_references_given(
    created_webhook_mock,
    updated_webhook_mock,
    staff_api_client,
    product,
    product_type,
    product_type_page_reference_attribute,
    permission_manage_products,
    warehouse,
    site_settings,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"

    product_type_page_reference_attribute.value_required = True
    product_type_page_reference_attribute.save(update_fields=["value_required"])

    product_type.variant_attributes.clear()
    product_type.variant_attributes.add(product_type_page_reference_attribute)
    ref_attr_id = graphene.Node.to_global_id(
        "Attribute", product_type_page_reference_attribute.id
    )
    file_url = f"http://{site_settings.site.domain}{settings.MEDIA_URL}test.jpg"

    values_count = product_type_page_reference_attribute.values.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "attributes": [{"id": ref_attr_id, "file": file_url}],
            "trackInventory": True,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()
    errors = content["errors"]
    data = content["productVariant"]

    assert not data
    assert len(errors) == 1
    assert errors[0]["code"] == ProductErrorCode.REQUIRED.name
    assert errors[0]["field"] == "attributes"
    assert errors[0]["attributes"] == [ref_attr_id]

    product_type_page_reference_attribute.refresh_from_db()
    assert product_type_page_reference_attribute.values.count() == values_count

    created_webhook_mock.assert_not_called()
    updated_webhook_mock.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_product_reference_attribute(
    created_webhook_mock,
    staff_api_client,
    product,
    product_type,
    product_type_product_reference_attribute,
    product_list,
    permission_manage_products,
    warehouse,
):
    query = CREATE_VARIANT_MUTATION
    product_id = graphene.Node.to_global_id("Product", product.pk)
    sku = "1"

    product_type_product_reference_attribute.value_required = True
    product_type_product_reference_attribute.save(update_fields=["value_required"])

    product_type.variant_attributes.clear()
    product_type.variant_attributes.add(product_type_product_reference_attribute)
    ref_attr_id = graphene.Node.to_global_id(
        "Attribute", product_type_product_reference_attribute.id
    )

    product_ref_1 = graphene.Node.to_global_id("Product", product_list[0].pk)
    product_ref_2 = graphene.Node.to_global_id("Product", product_list[1].pk)

    values_count = product_type_product_reference_attribute.values.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.pk),
            "quantity": 20,
        }
    ]

    variables = {
        "input": {
            "product": product_id,
            "sku": sku,
            "stocks": stocks,
            "attributes": [
                {"id": ref_attr_id, "references": [product_ref_1, product_ref_2]}
            ],
            "trackInventory": True,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)["data"]["productVariantCreate"]
    flush_post_commit_hooks()

    assert not content["errors"]
    data = content["productVariant"]
    assert data["sku"] == sku
    variant_id = data["id"]
    _, variant_pk = graphene.Node.from_global_id(variant_id)
    assert (
        data["attributes"][0]["attribute"]["slug"]
        == product_type_product_reference_attribute.slug
    )
    expected_values = [
        {
            "slug": f"{variant_pk}_{product_list[0].pk}",
            "file": None,
            "richText": None,
            "plainText": None,
            "reference": product_ref_1,
            "name": product_list[0].name,
            "boolean": None,
            "date": None,
            "dateTime": None,
        },
        {
            "slug": f"{variant_pk}_{product_list[1].pk}",
            "file": None,
            "richText": None,
            "plainText": None,
            "reference": product_ref_2,
            "name": product_list[1].name,
            "boolean": None,
            "date": None,
            "dateTime": None,
        },
    ]
    for value in expected_values:
        assert value in data["attributes"][0]["values"]
    assert len(data["stocks"]) == 1
    assert data["stocks"][0]["quantity"] == stocks[0]["quantity"]
    assert data["stocks"][0]["warehouse"]["slug"] == warehouse.slug

    product_type_product_reference_attribute.refresh_from_db()
    assert product_type_product_reference_attribute.values.count() == values_count + 2

    created_webhook_mock.assert_called_once_with(product.variants.last())


@patch("saleor.plugins.manager.PluginsManager.product_variant_updated")
@patch("saleor.plugins.manager.PluginsManager.product_variant_created")
def test_create_variant_with_product_reference_attribute_no_references_given(
    created_webhook_mock,
    updated_webhook_mock,
    staff_api_client,
    produc