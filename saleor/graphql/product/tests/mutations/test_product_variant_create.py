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