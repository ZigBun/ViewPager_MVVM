import json
from unittest import mock

import graphene
import pytest
from django.utils.functional import SimpleLazyObject
from django.utils.text import slugify
from freezegun import freeze_time

from .....attribute.error_codes import AttributeErrorCode
from .....attribute.models import Attribute
from .....core.utils.json_serializer import CustomJsonEncoder
from .....webhook.event_types import WebhookEventAsyncType
from .....webhook.payloads import generate_meta, generate_requestor
from ....core.enums import MeasurementUnitsEnum
from ....tests.utils import get_graphql_content
from ...enums import AttributeEntityTypeEnum, AttributeInputTypeEnum, AttributeTypeEnum

CREATE_ATTRIBUTE_MUTATION = """
    mutation createAttribute(
        $input: AttributeCreateInput!
    ){
        attributeCreate(input: $input) {
            errors {
                field
                message
                code
            }
            attribute {
                name
                slug
                type
                unit
                inputType
                entityType
                filterableInStorefront
                filterableInDashboard
                availableInGrid
                storefrontSearchPosition
                externalReference
                choices(first: 10) {
                    edges {
                        node {
                            name
                            slug
                            value
                            file {
                                url
                                contentType
                            }
                        }
                    }
                }
                productTypes(first: 10) {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        }
    }
"""


def test_create_attribute_and_attribute_values(
    staff_api_client,
    permission_manage_product_types_and_attributes,
    permission_manage_products,
):
    # given
    query = CREATE_ATTRIBUTE_MUTATION

    attribute_name = "Example name"
    name = "Value name"
    external_reference = "test-ext-ref"
    variables = {
        "input": {
            "name": attribute_name,
            "externalReference": external_reference,
            "values": [{"name": name}],
            "type": AttributeTypeEnum.PRODUCT_TYPE.name,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        query,
        variables,
        permissions=[
            permission_manage_product_types_and_attributes,
            permission_manage_products,
        ],
    )

    # then
    content = get_graphql_content(response)
    assert not content["data"]["attributeCreate"]["errors"]
    data = content["data"]["attributeCreate"]

    # Check if the attribute was correctly created
    assert data["attribute"]["name"] == attribute_name
    assert data["attribute"]["slug"] == slugify(
        attribute_name
    ), "The default slug should be the slugified name"
    assert (
        data["attribute"]["productTypes"]["edges"] == []
    ), "The attribute should not have been assigned to a product type"
    assert data["attribute"]["externalReference"] == external_reference

    # Check if the attribute values were correctly created
    assert len(data["attribute"]["choices"]) == 1
    assert data["attribute"]["type"] == AttributeTypeEnum.PRODUCT_TYPE.name
    assert data["attribute"]["choices"]["edges"][0]["node"]["name"] == name
    assert data["attribute"]["choices"]["edges"][0]["node"]["slug"] == slugify(name)


@freeze_time("2022-05-12 12:00:00")
@mock.patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@mock.patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_create_attribute_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_api_client,
    permission_manage_product_types_and_attributes,
    permission_manage_products,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    attribute_name = "Example name"
    name = "Value name"
    variables = {
        "input": {
            "name": attribute_name,
            "values": [{"name": name}],
            "type": AttributeTypeEnum.PRODUCT_TYPE.name,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        CREATE_ATTRIBUTE_MUTATION,
        variables,
        permissions=[
            permission_manage_product_types_and_attributes,
            permission_manage_products,
        ],
    )
    content = get_graphql_content(response)
    data = content["data"]["attributeCreate"]
    attribute = Attribute.objects.last()

    # then
    assert not data["errors"]
    assert data["attribute"]

    mocked_webhook_trigger.assert_called_once_with(
        json.dumps(
            {
                "id": graphene.Node.to_global_id("Attribute", attribute.id),
                "name": attribute.name,
                "slug": attribute.slug,
                "meta": generate_meta(
                    requestor_data=generate_requestor(
                        SimpleLazyObject(lambda: staff_api_client.user)
                    )
                ),
            },
            cls=CustomJsonEncoder,
        ),
        WebhookEventAsyncType.ATTRIBUTE_CREATED,
        [any_webhook],
        attribute,
        SimpleLazyObject(lambda: staff_api_client.user),
    )


def test_create_numeric_attribute_and_attribute_values(
    staff_api_client,
    permission_manage_product_types_and_attributes,
    permission_manage_products,
):
    # given
    query = CREATE_ATTRIBUTE_MUTATION

    attribute_name = "Example numeric attribute name"
    name = "12.1"
    variables = {
        "input": {
            "name": attribute_name,
            "values": [{"name": name}],
            "type": AttributeTypeEnum.PRODUCT_TYPE.name,
            "unit": MeasurementUnitsEnum.M.name,
            "inputType": AttributeInputTypeEnum.NUMERIC.name,
            "filterableInStorefront": True,
            "filterableInDashboard": True,
            "availableInGrid": True,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        query,
        variables,
        permissions=[
            permission_manage_product_types_and_attributes,
            permission_manage_products,
        ],
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["attributeCreate"]
    assert len(data["errors"]) == 1
    assert data["errors"][0]["code"] == AttributeErrorCode.INVALID.name
    assert data["errors"][0]["field"] == "values"


def test_create_numeric_attribute_and_attribute_values_not_numeric_value_provided(
    staff_api_client,
    permission_manage_product_types_and_attributes,
    permission_manage_products,
):
    # given
    query = CREATE_ATTRIBUTE_MUTATION

    attribute_name = "Example numeric attribute name"
    name = "Width"
    variables = {
        "input": {
            "name": attribute_name,
            "values": [{"name": name}],
            "type": AttributeTypeEnum.PRODUCT_TYPE.name,
            "unit": MeasurementUnitsEnum.M.name,
            "inputType": AttributeInputTypeEnum.NUMERIC.name,
            "filterableInStorefront": True,
            "filterableInDashboard": True,
            "availableInGrid": True,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        query,
        variables,
        permissions=[
            permission_manage_product_types_and_attributes,
            permission_manage_products,
        ],
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["attributeCreate"]
    errors = content["data"]["attributeCreate"]["errors"]

    assert not data["attribute"]
    assert len(errors) == 1
    assert errors[0]["field"] == "values"
    assert errors[0]["code"] == AttributeErrorCode.INVALID.name


def test_create_swatch_attribute_and_attribute_values_only_name_provided(
    staff_api_client,
    permission_manage_product_types_and_attributes,
    permission_manage_products,
):
    # given
    query = CREATE_ATTRIBUTE_MUTATION

    attribute_name = "Example numeric attribute name"
    name = "Pink"
    variables = {
        "input": {
            "name": attribute_name,
            "values": [{"name": name}],
            "type": AttributeTypeEnum.PRODUCT_TYPE.name,
            "inputType": AttributeInputTypeEnum.SWATCH.name,
            "filterableInStorefront": True,
            "filterableInDashboard": True,
            "availableInGrid": True,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        query,
        variables,
        permissions=[
            permission_manage_product_types_and_attributes,
            permission_manage_products,
        ],
    )

    # then
    content = get_graphql_content(response)
    assert not content["data"]["attributeCreate"]["errors"]
    data = content["data"]["attributeCreate"]

    # Check if the attribute was correctly created
    assert data["attribute"]["name"] == attribute_name
    assert data["attribute"]["slug"] == slugify(
        attribute_name
    ), "The default slug should be the slugified name"
    assert (
        data["attribute"]["productTypes"]["edges"] == []
    ), "The attribute should not have been assigned to a product type"

    # Check if the attribute values were correctly created
    assert len(data["attribute"]["choices"]) == 1
    assert data["attribute"]["type"] == AttributeTypeEnum.PRODUCT_TYPE.name
    assert data["attribute"]["unit"] is None
    assert data["attribute"]["inputType"] == AttributeInputTypeEnum.SWATCH.name
    assert data["attribut