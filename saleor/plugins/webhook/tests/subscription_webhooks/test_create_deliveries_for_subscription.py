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
    deliveries = create_deliveries_for_subscriptions(event_type, address, webhooks)

    # then
    expected_payload = json.dumps({"address": generate_address_payload(address)})
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_app_installed(app, subscription_app_installed_webhook):
    # given
    webhooks = [subscription_app_installed_webhook]
    event_type = WebhookEventAsyncType.APP_INSTALLED
    app_id = graphene.Node.to_global_id("App", app.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, app, webhooks)

    # then
    expected_payload = generate_app_payload(app, app_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_app_updated(app, subscription_app_updated_webhook):
    # given
    webhooks = [subscription_app_updated_webhook]
    event_type = WebhookEventAsyncType.APP_UPDATED
    app_id = graphene.Node.to_global_id("App", app.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, app, webhooks)

    # then
    expected_payload = generate_app_payload(app, app_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_app_deleted(app, subscription_app_deleted_webhook):
    # given
    webhooks = [subscription_app_deleted_webhook]

    id = app.id
    app.delete()
    app.id = id

    event_type = WebhookEventAsyncType.APP_DELETED
    app_id = graphene.Node.to_global_id("App", app.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, app, webhooks)

    # then
    expected_payload = generate_app_payload(app, app_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


@pytest.mark.parametrize("status", [True, False])
def test_app_status_changed(status, app, subscription_app_status_changed_webhook):
    # given
    webhooks = [subscription_app_status_changed_webhook]

    app.is_active = status
    app.save(update_fields=["is_active"])

    event_type = WebhookEventAsyncType.APP_STATUS_CHANGED
    app_id = graphene.Node.to_global_id("App", app.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, app, webhooks)

    # then
    expected_payload = generate_app_payload(app, app_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_attribute_created(color_attribute, subscription_attribute_created_webhook):
    # given
    webhooks = [subscription_attribute_created_webhook]
    event_type = WebhookEventAsyncType.ATTRIBUTE_CREATED

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, color_attribute, webhooks
    )

    # then
    expected_payload = generate_attribute_payload(color_attribute)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_attribute_updated(color_attribute, subscription_attribute_updated_webhook):
    # given
    webhooks = [subscription_attribute_updated_webhook]
    event_type = WebhookEventAsyncType.ATTRIBUTE_UPDATED

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, color_attribute, webhooks
    )

    # then
    expected_payload = generate_attribute_payload(color_attribute)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_attribute_deleted(color_attribute, subscription_attribute_deleted_webhook):
    # given
    webhooks = [subscription_attribute_deleted_webhook]

    id = color_attribute.id
    color_attribute.delete()
    color_attribute.id = id

    event_type = WebhookEventAsyncType.ATTRIBUTE_DELETED

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, color_attribute, webhooks
    )

    # then
    expected_payload = generate_attribute_payload(color_attribute)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_attribute_value_created(
    pink_attribute_value, subscription_attribute_value_created_webhook
):
    # given
    webhooks = [subscription_attribute_value_created_webhook]
    event_type = WebhookEventAsyncType.ATTRIBUTE_VALUE_CREATED

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, pink_attribute_value, webhooks
    )

    # then
    expected_payload = generate_attribute_value_payload(pink_attribute_value)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_attribute_value_updated(
    pink_attribute_value, subscription_attribute_value_updated_webhook
):
    # given
    webhooks = [subscription_attribute_value_updated_webhook]
    event_type = WebhookEventAsyncType.ATTRIBUTE_VALUE_UPDATED

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, pink_attribute_value, webhooks
    )

    # then
    expected_payload = generate_attribute_value_payload(pink_attribute_value)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_attribute_value_deleted(
    pink_attribute_value, subscription_attribute_value_deleted_webhook
):
    # given
    webhooks = [subscription_attribute_value_deleted_webhook]

    id = pink_attribute_value.id
    pink_attribute_value.delete()
    pink_attribute_value.id = id

    event_type = WebhookEventAsyncType.ATTRIBUTE_VALUE_DELETED

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, pink_attribute_value, webhooks
    )

    # then
    expected_payload = generate_attribute_value_payload(pink_attribute_value)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_category_created(
    categories_tree_with_published_products,
    subscription_category_created_webhook,
):
    # given
    parent_category = categories_tree_with_published_products
    webhooks = [subscription_category_created_webhook]
    event_type = WebhookEventAsyncType.CATEGORY_CREATED
    expected_payload = generate_category_payload(parent_category)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, parent_category, webhooks
    )

    # then
    assert deliveries[0].payload.payload == json.dumps(expected_payload)
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_category_updated(
    categories_tree_with_published_products,
    subscription_category_updated_webhook,
    channel_USD,
):
    # given
    parent_category = categories_tree_with_published_products
    webhooks = [subscription_category_updated_webhook]
    event_type = WebhookEventAsyncType.CATEGORY_UPDATED
    expected_payload = generate_category_payload(parent_category)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, parent_category, webhooks
    )

    # then
    assert deliveries[0].payload.payload == json.dumps(expected_payload)
    assert l