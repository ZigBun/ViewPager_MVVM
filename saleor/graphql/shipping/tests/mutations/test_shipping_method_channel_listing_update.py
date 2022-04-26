import json
from unittest.mock import patch

import graphene
import pytest
from django.utils.functional import SimpleLazyObject
from freezegun import freeze_time

from .....core.utils.json_serializer import CustomJsonEncoder
from .....shipping.error_codes import ShippingErrorCode
from .....shipping.models import ShippingMethodChannelListing
from .....webhook.event_types import WebhookEventAsyncType
from .....webhook.payloads import generate_meta, generate_requestor
from ....tests.utils import assert_negative_positive_decimal_value, get_graphql_content

SHIPPING_METHOD_CHANNEL_LISTING_UPDATE_MUTATION = """
mutation UpdateShippingMethodChannelListing(
    $id: ID!
    $input: ShippingMethodChannelListingInput!
) {
    shippingMethodChannelListingUpdate(id: $id, input: $input) {
        errors {
            field
            message
            code
            channels
        }
        shippingMethod {
            name
            channelListings {
                price {
                    amount
                }
                maximumOrderPrice {
                    amount
                }
                minimumOrderPrice {
                    amount
                }
                channel {
                    slug
                }
            }
        }
    }
}
"""


def test_shipping_method_channel_listing_create_as_staff_user(
    staff_api_client,
    shipping_method,
    permission_manage_shipping,
    channel_PLN,
):
    # given
    shipping_method.shipping_zone.channels.add(channel_PLN)
    shipping_method_id = graphene.Node.to_global_id(
        "ShippingMethodType", shipping_method.pk
    )
    channel_id = graphene.Node.to_global_id("Channel", channel_PLN.id)
    price = 1
    min_value = 2
    max_value = 3

    variables = {
        "id": shipping_method_id,
        "input": {
            "addChannels": [
                {
                    "channelId": channel_id,
                    "price": price,
                    "minimumOrderPrice": min_value,
                    "maximumOrderPrice": max_value,
                }
            ]
        },
    }

    # when

    response = staff_api_client.post_graphql(
        SHIPPING_METHOD_CHANNEL_LISTING_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_shipping,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["shippingMethodChannelListingUpdate"]
    shipping_method_data = data["shippingMethod"]
    assert not data["errors"]
    assert shipping_method_data["name"] == shipping_method.name

    assert shipping_method_data["channelListings"][1]["price"]["amount"] == price
    assert (
        shipping_method_data["channelListings"][1]["maximumOrderPrice"]["amount"]
        == max_value
    )
    assert (
        shipping_method_data["channelListings"][1]["minimumOrderPrice"]["amount"]
        == min_value
    )
    assert (
        shipping_method_data["channelListings"][1]["channel"]["slug"]
        == channel_PLN.slug
    )


def test_shipping_method_channel_listing_update_allow_to_set_null_for_limit_fields(
    staff_api_client,
    shipping_method,
    permission_manage_shipping,
    channel_PLN,
):
    # given
    shipping_method.shipping_zone.channels.add(channel_PLN)
    shipping_method_id = graphene.Node.to_global_id(
        "ShippingMethodType", shipping_method.pk
    )
    channel_listing = shipping_method.channel_listings.all()[0]
    channel = channel_listing.channel
    channel_id = graphene.Node.to_global_id("Channel", channel.id)
    channel_listing.minimum_order_price_amount = 2
    channel_listing.maximum_order_price_amount = 5
    channel_listing.save(
        update_fields=["minimum_order_price_amount", "maximum_order_price_amount"]
    )
    price = 3

    variables = {
        "id": shipping_method_id,
        "input": {
            "addChannels": [
                {
                    "channelId": channel_id,
                    "price": price,
                    "minimumOrderPrice": None,
                    "maximumOrderP