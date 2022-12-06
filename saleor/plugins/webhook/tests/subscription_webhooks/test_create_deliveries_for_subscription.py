import json
from unittest.mock import patch

import graphene
import pytest
from freezegun import freeze_time

from .....channel.models import Channel
from .....giftcard.models import GiftCard
from .....graphql.webhook.subscription_query import SubscriptionQuery
from .....menu.models import Menu, MenuItem
from .....product.models import Category
from .....shipping.models import ShippingMethod, ShippingZone
from .....webhook.event_types import WebhookEventAsyncType, WebhookEventSyncType
from ...tasks import create_deliveries_for_subscriptions, logger
from . import subscription_queries
from .payloads import (
    generate_address_payload,
    generate_app_payload,
    generate_attribute_payload,
    generate_attribute_value_payload,
    generate_category_payload,
    generate_collection_payload,
    generate_customer_payload,
    generate_fulfillment_payload,
    generate_gift_card_payload,
    generate_invoice_payload,
    generate_menu_item_payload,
    generate_menu_payload,
    generate_page_payload,
    generate_page_type_payload,
    generate_permission_group_payload,
    generate_sale_payload,
    generate_shipping_method_payload,
    generate_staff_payload,
    generate_voucher_created_payload_with_meta,
    generate_voucher_payload,
    generate_warehouse_payload,
)


@freeze_time("2022-05-12 12:00:00")
@pytest.mark.parametrize("requestor_type", ["user", "app", "anonymous"])
def test_subscription_query_with_meta(
    requestor_type,
    voucher,
    staff_user,
    app_with_token,
    subscription_voucher_webhook_with_meta,
):
    # given
    requestor_map = {
        "user": staff_user,
        "app": app_with_token,
        "anonymous": None,
    }
    webhooks = [subscription_voucher_webhook_with_meta]
    event_type = WebhookEventAsyncType.VOUCHER_CREATED
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.id)

    requestor = requestor_map[requestor_type]

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, voucher, webhooks, requestor
    )

    # then
    expected_payload = generate_voucher_created_payload_with_meta(
        voucher,
        voucher_id,
        requestor,
        requestor_type,
        subscription_voucher_webhook_with_meta.app,
    )
    assert json.loads(deliveries[0].payload.payload) == json.loads(expected_payload)
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_address_created(address, subscription_address_created_webhook):
    # given
    webhooks = [subscription_address_created_webhook]
    event_type = WebhookEventAsyncType.ADDRESS_CREATED

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, address, webhooks)

    # then
    expected_payload = json.dumps({"address": generate_address_payload(address)})

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_address_updated(address, subscription_address_updated_webhook):
    # given
    webhooks = [subscription_address_updated_webhook]
    event_type = WebhookEventAsyncType.ADDRESS_UPDATED

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, address, webhooks)

    # then
    expected_payload = json.dumps({"address": generate_address_payload(address)})
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_address_deleted(address, subscription_address_deleted_webhook):
    # given
    webhooks = [subscription_address_deleted_webhook]

    id = address.id
    address.delete()
    address.id = id

    event_type = WebhookEventAsyncType.ADDRESS_DELETED

    # when
    deliveries = create_deliveries_for_subscriptions(event_type,