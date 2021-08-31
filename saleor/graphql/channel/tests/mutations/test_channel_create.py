import json
from unittest import mock

import graphene
from django.utils.functional import SimpleLazyObject
from django.utils.text import slugify
from freezegun import freeze_time

from .....channel.error_codes import ChannelErrorCode
from .....channel.models import Channel
from .....core.utils.json_serializer import CustomJsonEncoder
from .....tax.models import TaxConfiguration
from .....webhook.event_types import WebhookEventAsyncType
from .....webhook.payloads import generate_meta, generate_requestor
from ....tests.utils import assert_no_permission, get_graphql_content
from ...enums import AllocationStrategyEnum

CHANNEL_CREATE_MUTATION = """
    mutation CreateChannel($input: ChannelCreateInput!){
        channelCreate(input: $input){
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
            }
        }
    }
"""


def test_channel_create_mutation_as_staff_user(
    permission_manage_channels,
    staff_api_client,
):
    # given
    name = "testName"
    slug = "test_slug"
    currency_code = "USD"
    default_country = "US"
    allocation_strategy = AllocationStrategyEnum.PRIORITIZE_HIGH_STOCK.name
    variables = {
        "input": {
            "name": name,
            "slug": slug,
            "currencyCode": currency_code,
            "defaultCountry": default_country,
            "stockSettings": {"allocationStrategy": allocation_strategy},
            "orderSettings": {
                "automaticallyConfirmAllNewOrders": False,
                "automaticallyFulfillNonShippableGiftCard": False,
            },
        }
    }

    # when
    response = staff_api_client.post_graphql(
        CHANNEL_CREATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["channelCreate"]
    assert not data["errors"]
    channel_data = data["channel"]
    channel = Channel.objects.get()
    assert channel_data["name"] == channel.name == name
    assert channel_data["slug"] == channel.slug == slug
    assert channel_data["currencyCode"] == channel.currency_code == currency_code
    assert (
        channel_data["defaultCountry"]["code"]
        == channel.default_country.code
        == default_country
    )
    assert channel_data["stockSettings"]["allocationStrategy"] == allocation_strategy
    assert channel_data["orderSettings"]["automaticallyConfirmAllNewOrders"] is False
    assert (
        channel_data["orderSettings"]["automaticallyFulfillNonShippableGiftCard"]
        is False
    )


def test_channel_create_mutation_as_app(
    permission_manage_channels,
    app_api_client,
):
    # given
    name = "testName"
    slug = "test_slug"
    currency_code = "USD"
    default_country = "US"
    variables = {
        "input": {
            "name": name,
            "slug": slug,
            "currencyCode": currency_code,
            "defaultCountry": default_country,
        }
    }

    # when
    response = app_api_client.post_graphql(
        CHANNEL_CREATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["channelCreate"]
    assert not data["errors"]
    channel_data = data["channel"]
    channel = Channel.objects.get()
    assert channel_data["name"] == channel.name == name
    assert channel_data["slug"] == channel.slug == slug
    assert channel_data["currencyCode"] == channel.currency_code == currency_code
    assert (
        channel_data["defaultCountry"]["code"]
        == channel.default_country.code
        == default_country
    )
    assert (
        channel_data["stockSettings"]["allocationStrategy"]
        == AllocationStrategyEnum.PRIORITIZE_SORTING_ORDER.name
    )
    assert channel_data["orderSettings"]["automaticallyConfirmAllNewOrders"] is True
    assert (
        channel_data["orderSettings"]["automaticallyFulfillNonShippableGiftCard"]
        is True
    )


def test_channel_create_mutation_as_customer(user_api_client):
    # given
    name = "testName"
    slug = "test_slug"
    currency_code = "USD"
    default_country = "US"
    allocation_strategy = AllocationStrategyEnum.PRIORITIZE_SORTING_ORDER.name
    variables = {
        "input": {
            "name": name,
            "slug": slug,
            "currencyCode": currency_code,
            "defaultCountry": default_country,
            "stockSettings": {"allocationStrategy": allocation_strategy},
            "orderSettings": {
                "automaticallyConfirmAllNewOrders": False,
                "automaticallyFulfillNonShippableGiftCard": False,
            },
        }
    }

    # when
    response = user_api_client.post_graphql(
        CHANNEL_CREATE_MUTATION,
        variables=variables,
        permissions=(),
    )

    # then
    assert_no_permission(response)


def test_channel_create_mutation_as_anonymous(api_client):
    # given
    name = "testName"
    slug = "test_slug"
    currency_code = "USD"
    default_country = "US"
    variables = {
        "input": {
            "name": name,
            "slug": slug,
            "currencyCode": currency_code,
            "defaultCountry": default_country,
        }
    }

    # when
    response = api_client.post_graphql(
        CHANNEL_CREATE_MUTATION,
        variables=variables,
        permissions=(),
    )

    # then
    assert_no_permission(response)


def test_channel_create_mutation_slugify_slug_field(
    permission_manage_channels,
    staff_api_client,
):
    # given
    name = "testName"
    slug = "Invalid slug"
    currency_code = "USD"
    default_country = "US"
    variables = {
        "input": {
            "name": name,
            "slug": slug,
            "currencyCode": currency_code,
            "defaultCountry": default_country,
        }
    }

    # when
    response = staff_api_client.post_graphql(
        CHANNEL_CREATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    channel_data = content["data"]["channelCreate"]["channel"]
    assert channel_data["slug"] == slugify(slug)


def test_channel_create_mutation_with_duplicated_slug(
    permission_manage_channels, staff_api_client, channel_USD
):
    # given
    name = "New Channel"
    slug = channel_USD.slug
    currency_code = "USD"
    default_country = "US"
    allocation_strategy = AllocationStrategyEnum.PRIORITIZE_SORTING_ORDER.name
    variables = {
        "input": {
            "name": name,
            "slug": slug,
            "currencyCode": currency_code,
            "defaultCountry": default_country,
            "stockSettings": {"allocationStrategy": allocation_strategy},
        }
    }

    # when
    response = staff_api_client.post_graphql(
        CHANNEL_CREATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    error = content["data"]["channelCreate"]["errors"][0]
    assert error["field"] == "slug"
    assert error["code"] == ChannelErrorCode.UNIQUE.name


def test_channel_create_mutation_with_shipping_zones(
    permission_manage_channels,
    staff_api_client,
    shipping_zones,
):
    # given
    name = "testName"
    slug = "test_slug"
    currency_code = "USD"
    default_country = "US"
    shipping_zones_ids = [
        graphene.Node.to_global_id("ShippingZone", zone.pk) for zone in shipping_zones
    ]
    allocation_strategy = AllocationStrategyEnum.PRIORITIZE_SORTING_ORDER.name
    variables = {
        "input": {
            "name": name,
            "slug": slug,
            "currencyCode": currency_code,
            "addShippingZones": shipping_zones_ids,
            "defaultCountry": default_country,
            "stockSettings": {"allocationStrategy": allocation_strategy},
        }
    }

    # when
    response = staff_api_client.post_graphql(
        CHANNEL_CREATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["channelCreate"]
    assert not data["errors"]
    channel_data = data["channel"]
    channel = Channel.objects.get(
        id=graphene.Node.from_global_id(channel_data["id"])[1]
    )
    assert channel_data["name"] == channel.name == name
    assert channel_data["slug"] == channel.slug == slug
    assert channel_data["currencyCode"] == channel.currency_code == currency_code
    for shipping_zone in shipping_zones:
        shipping_zone.channels.get(slug=slug)
    assert channel_data["s