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
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = "new_slug"
    variables = {"id": channel_id, "input": {"name": name, "slug": slug}}

    # when
    response = api_client.post_graphql(
        CHANNEL_UPDATE_MUTATION,
        variables=variables,
        permissions=(),
    )

    # then
    assert_no_permission(response)


def test_channel_update_mutation_slugify_slug_field(
    permission_manage_channels, staff_api_client, channel_USD
):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "testName"
    slug = "Invalid slug"
    variables = {"id": channel_id, "input": {"name": name, "slug": slug}}

    # when
    response = staff_api_client.post_graphql(
        CHANNEL_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    channel_data = content["data"]["channelUpdate"]["channel"]
    assert channel_data["slug"] == slugify(slug)


def test_channel_update_mutation_with_duplicated_slug(
    permission_manage_channels, staff_api_client, channel_USD, channel_PLN
):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "New Channel"
    slug = channel_PLN.slug
    variables = {"id": channel_id, "input": {"name": name, "slug": slug}}

    # when
    response = staff_api_client.post_graphql(
        CHANNEL_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_channels,),
    )
    content = get_graphql_content(response)

    # then
    error = content["data"]["channelUpdate"]["errors"][0]
    assert error["field"] == "slug"
    assert error["code"] == ChannelErrorCode.UNIQUE.name


def test_channel_update_mutation_only_name(
    permission_manage_channels, staff_api_client, channel_USD
):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = channel_USD.slug
    variables = {"id": channel_id, "input": {"name": name}}

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


def test_channel_update_mutation_only_slug(
    permission_manage_channels, staff_api_client, channel_USD
):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = channel_USD.name
    slug = "new_slug"
    variables = {"id": channel_id, "input": {"slug": slug}}

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


def test_channel_update_mutation_add_shipping_zone(
    permission_manage_channels, staff_api_client, channel_USD, shipping_zone
):
    # given
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = "new_slug"
    shipping_zone_id = graphene.Node.to_global_id("ShippingZone", shipping_zone.pk)
    variables = {
        "id": channel_id,
        "input": {"name": name, "slug": slug, "addShippingZones": [shipping_zone_id]},
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
    shipping_zone.refresh_from_db()
    assert channel_data["name"] == channel_USD.name == name
    assert channel_data["slug"] == channel_USD.slug == slug
    assert channel_data["currencyCode"] == channel_USD.currency_code == "USD"
    actual_shipping_zone = channel_USD.shipping_zones.first()
    assert actual_shipping_zone == shipping_zone


@patch(
    "saleor.graphql.channel.mutations.channel_update."
    "drop_invalid_shipping_methods_relations_for_given_channels.delay"
)
def test_channel_update_mutation_remove_shipping_zone(
    mocked_drop_invalid_shipping_methods_relations,
    permission_manage_channels,
    staff_api_client,
    channel_USD,
    shipping_zones,
    warehouses,
    channel_PLN,
):
    # given
    channel_USD.shipping_zones.add(*shipping_zones)
    channel_PLN.shipping_zones.add(*shipping_zones)

    for warehouse in warehouses:
        warehouse.shipping_zones.add(*shipping_zones)

    # add another common channel with zone to warehouses on index 1
    channel_PLN.warehouses.add(warehouses[0])

    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = "new_slug"
    shipping_zone = shipping_zones[0]
    shipping_method_ids = shipping_zone.shipping_methods.values_list("id", flat=True)
    remove_shipping_zone = graphene.Node.to_global_id("ShippingZone", shipping_zone.pk)
    variables = {
        "id": channel_id,
        "input": {
            "name": name,
            "slug": slug,
            "removeShippingZones": [remove_shipping_zone],
        },
    }
    assert channel_USD.shipping_method_listings.filter(
        shipping_method__shipping_zone=shipping_zone
    )

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
    assert not channel_USD.shipping_method_listings.filter(
        shipping_method__shipping_zone=shipping_zone
    )
    mocked_drop_invalid_shipping_methods_relations.assert_called_once_with(
        list(shipping_method_ids), [channel_USD.id]
    )
    # ensure one warehouse was removed from shipping zone as they do not have
    # common channel anymore
    assert warehouses[0].id not in shipping_zones[0].warehouses.values("id")

    # ensure another shipping zone has all warehouses assigned
    for zone in shipping_zones[1:]:
        assert zone.warehouses.count() == len(warehouses)


def test_channel_update_mutation_add_and_remove_shipping_zone(
    permission_manage_channels,
    staff_api_client,
    channel_USD,
    shipping_zones,
    shipping_zone,
):
    # given
    channel_USD.shipping_zones.add(*shipping_zones)
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    name = "newName"
    slug = "new_slug"
    remove_shipping_zone = graphene.Node.to_global_id(
        "ShippingZone", shipping_zones[0].pk
    )
    add_shipping_zone = graphene.