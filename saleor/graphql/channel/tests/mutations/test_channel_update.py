import json
from unittest.mock import patch

import graphene
import pytest
from django.utils.functional import SimpleLazyObject
from django.utils.text import slugify
from freezegun import freeze_time

from .....channel.error_codes import ChannelErrorCode
from .....core.utils.json_serializer import CustomJsonEncoder
from .....webhook.event_types import WebhookEventAsyncType
from .....webhook.payloads import generate_meta, generate_requestor
from ....tests.utils import assert_no_permission, get_graphql_content
from ...enums import AllocationStrategyEnum

CHANNEL_UPDATE_MUTATION = """
    mutation UpdateChannel($id: ID!,$input: ChannelUpdateInput!){
        channelUpdate(id: $id, input: $input){
            channel{
                id
                name
                slug
                currencyCode
                defaultCountry {
                    code
                    country
                }
                warehouses {
                    slug
                }
                stockSettings {
                    allocationStrategy
                }
                orderSettings {
                    automaticallyConfirmAllNewOrders
                    automaticallyFulfillNonShippableGiftCard
                }
            }
            errors{
                field
                code
                message
                shippingZones
                warehouses
            }
        }
    }
"""


def test_channel_update_mutation_as_staff_user(
    permission_manage_channels, staff_api_client, channel_USD
):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = "new_slug"
    default_country = "FR"
    allocation_strategy = AllocationStrategyEnum.PRIORITIZE_SORTING_ORDER.name
    variables = {
        "id": channel_id,
        "input": {
            "name": name,
            "slug": slug,
            "defaultCountry": default_country,
            "stockSettings": {"allocationStrategy": allocation_strategy},
            "orderSettings": {
                "automaticallyConfirmAllNewOrders": False,
                "automaticallyFulfillNonShippableGiftCard": False,
            },
        },
    }

    # when
    response = staff_api_client.post_graphql(
        CHANNEL_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["channelUpdate"]
    assert not data["errors"]
    channel_data = data["channel"]
    channel_USD.refresh_from_db()
    assert channel_data["name"] == channel_USD.name == name
    assert channel_data["slug"] == channel_USD.slug == slug
    assert channel_data["currencyCode"] == channel_USD.currency_code == "USD"
    assert (
        channel_data["defaultCountry"]["code"]
        == channel_USD.default_country.code
        == default_country
    )
    assert channel_data["stockSettings"]["allocationStrategy"] == allocation_strategy
    assert channel_data["orderSettings"]["automaticallyConfirmAllNewOrders"] is False
    assert (
        channel_data["orderSettings"]["automaticallyFulfillNonShippableGiftCard"]
        is False
    )


def test_channel_update_mutation_as_app(
    permission_manage_channels, app_api_client, channel_USD
):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = "new_slug"
    variables = {"id": channel_id, "input": {"name": name, "slug": slug}}

    # when
    response = app_api_client.post_graphql(
        CHANNEL_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["channelUpdate"]
    assert not data["errors"]
    channel_data = data["channel"]
    channel_USD.refresh_from_db()
    assert channel_data["name"] == channel_USD.name == name
    assert channel_data["slug"] == channel_USD.slug == slug
    assert channel_data["currencyCode"] == channel_USD.currency_code == "USD"


def test_channel_update_mutation_as_customer(user_api_client, channel_USD):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = "new_slug"
    variables = {"id": channel_id, "input": {"name": name, "slug": slug}}

    # when
    response = user_api_client.post_graphql(
        CHANNEL_UPDATE_MUTATION,
        variables=variables,
        permissions=(),
    )

    # then
    assert_no_permission(response)


def test_channel_update_mutation_as_anonymous(api_client, channel_USD):
    # given
    channel_id 