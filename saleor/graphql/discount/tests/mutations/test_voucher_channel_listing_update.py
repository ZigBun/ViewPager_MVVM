import json
from unittest.mock import patch

import graphene
from django.utils.functional import SimpleLazyObject
from freezegun import freeze_time

from .....core.utils.json_serializer import CustomJsonEncoder
from .....discount import DiscountValueType
from .....discount.error_codes import DiscountErrorCode
from .....webhook.event_types import WebhookEventAsyncType
from .....webhook.payloads import generate_meta, generate_requestor
from ....tests.utils import assert_no_permission, get_graphql_content

VOUCHER_CHANNEL_LISTING_UPDATE_MUTATION = """
mutation UpdateVoucherChannelListing($id: ID!, $input: VoucherChannelListingInput!) {
    voucherChannelListingUpdate(id: $id, input: $input) {
        errors {
            field
            message
            code
            channels
        }
        voucher {
            code
            channelListings {
                channel{
                    slug
                }
                discountValue
                currency
                minSpent {
                    currency
                    amount
                }
            }
        }
    }
}
"""


def test_voucher_channel_listing_create_as_staff(
    staff_api_client, voucher_without_channel, permission_manage_discounts, channel_USD
):
    # given
    voucher = voucher_without_channel
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.pk)
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    discount_value = 5.5
    variables = {
        "id": voucher_id,
        "input": {
            "addChannels": [{"channelId": channel_id, "discountValue": discount_value}]
        },
    }

    # when
    response = staff_api_client.post_graphql(
        VOUCHER_CHANNEL_LISTING_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_discounts,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["voucherChannelListingUpdate"]["voucher"]
    assert not content["data"]["voucherChannelListingUpdate"]["errors"]
    channel_listing = data["channelListings"]
    assert channel_listing[0]["channel"]["slug"] == channel_USD.slug
    assert channel_listing[0]["discountValue"] == discount_value
    assert channel_listing[0]["currency"] == channel_USD.currency_code


def test_voucher_channel_listing_update_as_app(
    app_api_client, voucher_without_channel, permission_manage_discounts, channel_USD
):
    # given
    voucher = voucher_without_channel
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.pk)
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    discount_value = 5.5
    variables = {
        "id": voucher_id,
        "input": {
            "addChannels": [{"channelId": channel_id, "discountValue": discount_value}]
        },
    }

    # when
    response = app_api_client.post_graphql(
        VOUCHER_CHANNEL_LISTING_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_discounts,),
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["voucherChannelListingUpdate"]["voucher"]
    assert not content["data"]["voucherChannelListingUpdate"]["errors"]
    channel_listing = data["channelListings"]
    assert channel_listing[0]["channel"]["slug"] == channel_USD.slug
    assert channel_listing[0]["discountValue"] == discount_value
    assert channel_listing[0]["currency"] == channel_USD.currency_code


def test_voucher_channel_listing_update_as_customer(
    user_api_client, voucher_without_channel, channel_USD
):
    # given
    voucher = voucher_without_channel
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.pk)
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    variables = {
        "id": voucher_id,
        "input": {"addChannels": [{"channelId": channel_id, "discountValue": 5.5}]},
    }

    # when
    response = user_api_client.post_graphql(
        VOUCHER_CHANNEL_LISTING_UPDATE_MUTATION,
        variables=variables,
    )

    # then
    assert_no_permission(response)


@freeze_time("2022-05-12 12:00:00")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_voucher_channel_listing_update_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    permission_manage_discounts,
    staff_api_client,
    voucher_without_channel,
    channel_USD,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    voucher = voucher_without_channel
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.pk)
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    variables = {
        "id": voucher_id,
        "input": {"addChannels": [{"channelId": channel_id, "discountValue": 5.5}]},
    }

    # when
    response = staff_api_client.post_graphql(
        VOUCHER_CHANNEL_LISTING_UPDATE_MUTATION,
        variables=variables,
        permissions=(permission_manage_discounts,),
    )
    content = get_graphql_content(response)

    # then
    assert content["data"]["voucherChannelListingUpdate"]["voucher"]
    mocked_webhook_trigger.assert_called_once_with(
        json.dumps(
            {
                "id": variables["id"],
                "name": voucher.name,
                "code": voucher.code,
                "meta": generate_meta(
                    requestor_data=generate_requestor(
                        SimpleLazyObject(lambda: staff_api_client.user)
                    )
                ),
            },
            cls=CustomJsonEncoder,
        ),
        WebhookEventAsyncType.VOUCHER_UPDATED,
        [any_webhook],
        voucher,
        SimpleLazyObject(lambda: staff_api_client.user),
    )


def test_voucher_channel_listing_update_as_anonymous(
    api_client, voucher_without_channel, channel_USD
):
    # given
    voucher = voucher_without_channel
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.pk)
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    variables = {
        "id": voucher_id,
        "input": {"addChannels": [{"channelId": channel_id, "discountValue": 5.5}]},
    }

    # when
    response = api_client.post_graphql(
        VOUCHER_CHANNEL_LISTING_UPDATE_MUTATION,
        variables=variables,
    )

    # then
    assert_no_permission(response)


def test_voucher_channel_listing_create_many_channel(
    staff_api_client,
    voucher_without_channel,
    permission_manage_discounts,
    channel_USD,
    channel_PLN,
):
    # given
    voucher = voucher_without_channel
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.pk)
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)
    channel_pln_id = graphene.Node.to_global_id("Channel", channel_PLN.id)
    discount_value = 5.5
    discount_value_pln = 50.5
    min_amount_spent = 10.1
    min_amount_spent_pln = 100.2
    variables = {
        "id": voucher_id,
        "input": {
            "addChannels": [
 