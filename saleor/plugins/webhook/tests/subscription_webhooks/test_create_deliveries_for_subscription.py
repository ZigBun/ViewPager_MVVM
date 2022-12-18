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
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_category_deleted(category, subscription_category_deleted_webhook):
    # given
    webhooks = [subscription_category_deleted_webhook]

    category_query = Category.objects.filter(pk=category.id)
    category_instances = [cat for cat in category_query]
    category_query.delete()

    event_type = WebhookEventAsyncType.CATEGORY_DELETED
    category_id = graphene.Node.to_global_id("Category", category_instances[0].id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, category_instances[0], webhooks
    )

    # then
    expected_payload = json.dumps({"category": {"id": category_id}})
    assert category_instances[0].id is not None
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_channel_created(channel_USD, subscription_channel_created_webhook):
    # given
    webhooks = [subscription_channel_created_webhook]
    event_type = WebhookEventAsyncType.CHANNEL_CREATED
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, channel_USD, webhooks)

    # then
    expected_payload = json.dumps({"channel": {"id": channel_id}})
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_channel_updated(channel_USD, subscription_channel_updated_webhook):
    # given
    webhooks = [subscription_channel_updated_webhook]
    event_type = WebhookEventAsyncType.CHANNEL_UPDATED
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, channel_USD, webhooks)

    # then
    expected_payload = json.dumps({"channel": {"id": channel_id}})
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_channel_deleted(channel_USD, subscription_channel_deleted_webhook):
    # given
    webhooks = [subscription_channel_deleted_webhook]

    channel_query = Channel.objects.filter(pk=channel_USD.id)
    channel_instances = [channel for channel in channel_query]
    channel_query.delete()

    event_type = WebhookEventAsyncType.CHANNEL_DELETED
    channel_id = graphene.Node.to_global_id("Channel", channel_instances[0].id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, channel_instances[0], webhooks
    )

    # then
    expected_payload = json.dumps({"channel": {"id": channel_id}})
    assert channel_instances[0].id is not None
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


@pytest.mark.parametrize("status", [True, False])
def test_channel_status_changed(
    status, channel_USD, subscription_channel_status_changed_webhook
):
    # given
    webhooks = [subscription_channel_status_changed_webhook]

    channel_USD.is_active = status
    channel_USD.save(update_fields=["is_active"])

    event_type = WebhookEventAsyncType.CHANNEL_STATUS_CHANGED
    channel_id = graphene.Node.to_global_id("Channel", channel_USD.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, channel_USD, webhooks)

    # then
    expected_payload = json.dumps({"channel": {"id": channel_id, "isActive": status}})
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_gift_card_created(gift_card, subscription_gift_card_created_webhook):
    # given
    webhooks = [subscription_gift_card_created_webhook]
    event_type = WebhookEventAsyncType.GIFT_CARD_CREATED
    gift_card_id = graphene.Node.to_global_id("GiftCard", gift_card.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, gift_card, webhooks)

    # then
    expected_payload = generate_gift_card_payload(gift_card, gift_card_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_gift_card_updated(gift_card, subscription_gift_card_updated_webhook):
    # given
    webhooks = [subscription_gift_card_updated_webhook]
    event_type = WebhookEventAsyncType.GIFT_CARD_UPDATED
    gift_card_id = graphene.Node.to_global_id("GiftCard", gift_card.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, gift_card, webhooks)

    # then
    expected_payload = generate_gift_card_payload(gift_card, gift_card_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_gift_card_deleted(gift_card, subscription_gift_card_deleted_webhook):
    # given
    webhooks = [subscription_gift_card_deleted_webhook]

    gift_card_query = GiftCard.objects.filter(pk=gift_card.id)
    gift_card_instances = [card for card in gift_card_query]
    gift_card_query.delete()

    event_type = WebhookEventAsyncType.GIFT_CARD_DELETED
    gift_card_id = graphene.Node.to_global_id("GiftCard", gift_card_instances[0].id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, gift_card_instances[0], webhooks
    )

    # then
    expected_payload = generate_gift_card_payload(gift_card, gift_card_id)
    assert gift_card_instances[0].id is not None
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


@pytest.mark.parametrize("status", [True, False])
def test_gift_card_status_changed(
    status, gift_card, subscription_gift_card_status_changed_webhook
):
    # given
    webhooks = [subscription_gift_card_status_changed_webhook]

    gift_card.is_active = status
    gift_card.save(update_fields=["is_active"])

    event_type = WebhookEventAsyncType.GIFT_CARD_STATUS_CHANGED
    gift_card_id = graphene.Node.to_global_id("GiftCard", gift_card.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, gift_card, webhooks)

    # then
    expected_payload = generate_gift_card_payload(gift_card, gift_card_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_gift_card_metadata_updated(
    gift_card, subscription_gift_card_metadata_updated_webhook
):
    # given
    webhooks = [subscription_gift_card_metadata_updated_webhook]
    event_type = WebhookEventAsyncType.GIFT_CARD_METADATA_UPDATED
    gift_card_id = graphene.Node.to_global_id("GiftCard", gift_card.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, gift_card, webhooks)

    # then
    expected_payload = generate_gift_card_payload(gift_card, gift_card_id)
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_menu_created(menu, subscription_menu_created_webhook):
    # given
    webhooks = [subscription_menu_created_webhook]
    event_type = WebhookEventAsyncType.MENU_CREATED
    menu_id = graphene.Node.to_global_id("Menu", menu.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, menu, webhooks)

    # then
    expected_payload = json.dumps(generate_menu_payload(menu, menu_id))
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_menu_updated(menu, subscription_menu_updated_webhook):
    # given
    webhooks = [subscription_menu_updated_webhook]
    event_type = WebhookEventAsyncType.MENU_UPDATED
    menu_id = graphene.Node.to_global_id("Menu", menu.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, menu, webhooks)

    # then
    expected_payload = json.dumps(generate_menu_payload(menu, menu_id))
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_menu_deleted(menu, subscription_menu_deleted_webhook):
    # given
    webhooks = [subscription_menu_deleted_webhook]

    menu_query = Menu.objects.filter(pk=menu.id)
    menu_instances = [menu for menu in menu_query]
    menu_query.delete()

    event_type = WebhookEventAsyncType.MENU_DELETED
    menu_id = graphene.Node.to_global_id("Menu", menu_instances[0].id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, menu_instances[0], webhooks
    )

    # then
    expected_payload = json.dumps(generate_menu_payload(menu, menu_id))
    assert menu_instances[0].id is not None
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_menu_item_created(menu_item, subscription_menu_item_created_webhook):
    # given
    webhooks = [subscription_menu_item_created_webhook]
    event_type = WebhookEventAsyncType.MENU_ITEM_CREATED
    menu_item_id = graphene.Node.to_global_id("MenuItem", menu_item.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, menu_item, webhooks)

    # then
    expected_payload = json.dumps(generate_menu_item_payload(menu_item, menu_item_id))
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_menu_item_updated(menu_item, subscription_menu_item_updated_webhook):
    # given
    webhooks = [subscription_menu_item_updated_webhook]
    event_type = WebhookEventAsyncType.MENU_ITEM_UPDATED
    menu_item_id = graphene.Node.to_global_id("MenuItem", menu_item.id)

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, menu_item, webhooks)

    # then
    expected_payload = json.dumps(generate_menu_item_payload(menu_item, menu_item_id))
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_menu_item_deleted(menu_item, subscription_menu_item_deleted_webhook):
    # given
    webhooks = [subscription_menu_item_deleted_webhook]

    menu_item_query = MenuItem.objects.filter(pk=menu_item.id)
    menu_item_instances = [menu for menu in menu_item_query]
    menu_item_query.delete()

    event_type = WebhookEventAsyncType.MENU_ITEM_DELETED
    menu_item_id = graphene.Node.to_global_id("MenuItem", menu_item_instances[0].id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, menu_item_instances[0], webhooks
    )

    # then
    expected_payload = json.dumps(
        generate_menu_item_payload(menu_item_instances[0], menu_item_id)
    )
    assert menu_item_instances[0].id is not None
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_shipping_price_created(
    shipping_method, subscription_shipping_price_created_webhook
):
    # given
    webhooks = [subscription_shipping_price_created_webhook]
    event_type = WebhookEventAsyncType.SHIPPING_PRICE_CREATED
    expected_payload = generate_shipping_method_payload(shipping_method)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, shipping_method, webhooks
    )

    # then
    assert deliveries[0].payload.payload == json.dumps(expected_payload)
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_shipping_price_updated(
    shipping_method, subscription_shipping_price_updated_webhook
):
    # given
    webhooks = [subscription_shipping_price_updated_webhook]
    event_type = WebhookEventAsyncType.SHIPPING_PRICE_UPDATED
    expected_payload = generate_shipping_method_payload(shipping_method)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, shipping_method, webhooks
    )

    # then
    assert deliveries[0].payload.payload == json.dumps(expected_payload)
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_shipping_price_deleted(
    shipping_method, subscription_shipping_price_deleted_webhook
):
    # given
    webhooks = [subscription_shipping_price_deleted_webhook]
    event_type = WebhookEventAsyncType.SHIPPING_PRICE_DELETED

    shipping_methods_query = ShippingMethod.objects.filter(pk=shipping_method.id)
    method_instances = [method for method in shipping_methods_query]
    shipping_methods_query.delete()

    shipping_method_id = graphene.Node.to_global_id(
        "ShippingMethodType", method_instances[0].id
    )

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, method_instances[0], webhooks
    )

    # then
    expected_payload = json.dumps(
        {"shippingMethod": {"id": shipping_method_id, "name": shipping_method.name}}
    )
    assert method_instances[0].id is not None
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_shipping_zone_created(
    shipping_zone, subscription_shipping_zone_created_webhook
):
    # given
    webhooks = [subscription_shipping_zone_created_webhook]
    event_type = WebhookEventAsyncType.SHIPPING_ZONE_CREATED
    shipping_zone_id = graphene.Node.to_global_id("ShippingZone", shipping_zone.id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, shipping_zone, webhooks
    )

    # then
    expected_payload = json.dumps(
        {
            "shippingZone": {
                "id": shipping_zone_id,
                "name": shipping_zone.name,
                "countries": [{"code": c.code} for c in shipping_zone.countries],
                "channels": [{"name": c.name} for c in shipping_zone.channels.all()],
            }
        }
    )

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_shipping_zone_updated(
    shipping_zone, subscription_shipping_zone_updated_webhook
):
    # given
    webhooks = [subscription_shipping_zone_updated_webhook]
    event_type = WebhookEventAsyncType.SHIPPING_ZONE_UPDATED
    shipping_zone_id = graphene.Node.to_global_id("ShippingZone", shipping_zone.id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, shipping_zone, webhooks
    )

    # then
    expected_payload = json.dumps(
        {
            "shippingZone": {
                "id": shipping_zone_id,
                "name": shipping_zone.name,
                "countries": [{"code": c.code} for c in shipping_zone.countries],
                "channels": [{"name": c.name} for c in shipping_zone.channels.all()],
            }
        }
    )
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_shipping_zone_deleted(
    shipping_zone, subscription_shipping_zone_deleted_webhook
):
    # given
    webhooks = [subscription_shipping_zone_deleted_webhook]
    event_type = WebhookEventAsyncType.SHIPPING_ZONE_DELETED

    shipping_zones_query = ShippingZone.objects.filter(pk=shipping_zone.id)
    zones_instances = [zone for zone in shipping_zones_query]
    shipping_zones_query.delete()

    shipping_zone_id = graphene.Node.to_global_id("ShippingZone", zones_instances[0].id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, zones_instances[0], webhooks
    )

    # then
    expected_payload = json.dumps(
        {
            "shippingZone": {"id": shipping_zone_id, "name": shipping_zone.name},
        }
    )
    assert zones_instances[0].id is not None
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_shipping_zone_metadata_updated(
    shipping_zone, subscription_shipping_zone_metadata_updated_webhook
):
    # given
    webhooks = [subscription_shipping_zone_metadata_updated_webhook]
    event_type = WebhookEventAsyncType.SHIPPING_ZONE_METADATA_UPDATED
    shipping_zone_id = graphene.Node.to_global_id("ShippingZone", shipping_zone.id)

    # when
    deliveries = create_deliveries_for_subscriptions(
        event_type, shipping_zone, webhooks
    )

    # then
    expected_payload = json.dumps(
        {
            "shippingZone": {
                "id": shipping_zone_id,
                "name": shipping_zone.name,
                "countries": [{"code": c.code} for c in shipping_zone.countries],
                "channels": [{"name": c.name} for c in shipping_zone.channels.all()],
            }
        }
    )
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_staff_created(staff_user, subscription_staff_created_webhook):
    # given
    webhooks = [subscription_staff_created_webhook]
    event_type = WebhookEventAsyncType.STAFF_CREATED
    expected_payload = json.dumps(generate_staff_payload(staff_user))

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, staff_user, webhooks)

    # then
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_staff_updated(staff_user, subscription_staff_updated_webhook):
    # given
    webhooks = [subscription_staff_updated_webhook]
    event_type = WebhookEventAsyncType.STAFF_UPDATED
    expected_payload = json.dumps(generate_staff_payload(staff_user))

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, staff_user, webhooks)

    # then
    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_staff_deleted(staff_user, subscription_staff_deleted_webhook):
    # given
    webhooks = [subscription_staff_deleted_webhook]
    id = staff_user.id
    staff_user.delete()
    staff_user.id = id

    event_type = WebhookEventAsyncType.STAFF_DELETED

    # when
    deliveries = create_deliveries_for_subscriptions(event_type, staff_user, webhooks)
    expected_payload = json.dumps(generate_staff_payload(staff_user))

    # then

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_product_created(product, subscription_product_created_webhook):
    webhooks = [subscription_product_created_webhook]
    event_type = WebhookEventAsyncType.PRODUCT_CREATED
    product_id = graphene.Node.to_global_id("Product", product.id)
    deliveries = create_deliveries_for_subscriptions(event_type, product, webhooks)
    expected_payload = json.dumps({"product": {"id": product_id}})

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_product_updated(product, subscription_product_updated_webhook):
    webhooks = [subscription_product_updated_webhook]
    event_type = WebhookEventAsyncType.PRODUCT_UPDATED
    product_id = graphene.Node.to_global_id("Product", product.id)
    deliveries = create_deliveries_for_subscriptions(event_type, product, webhooks)
    expected_payload = json.dumps({"product": {"id": product_id}})

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_product_deleted(product, subscription_product_deleted_webhook):
    webhooks = [subscription_product_deleted_webhook]
    event_type = WebhookEventAsyncType.PRODUCT_DELETED
    product_id = graphene.Node.to_global_id("Product", product.id)
    deliveries = create_deliveries_for_subscriptions(event_type, product, webhooks)
    expected_payload = json.dumps({"product": {"id": product_id}})

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_product_metadata_updated(
    product, subscription_product_metadata_updated_webhook
):
    webhooks = [subscription_product_metadata_updated_webhook]
    event_type = WebhookEventAsyncType.PRODUCT_METADATA_UPDATED
    product_id = graphene.Node.to_global_id("Product", product.id)
    deliveries = create_deliveries_for_subscriptions(event_type, product, webhooks)
    expected_payload = json.dumps({"product": {"id": product_id}})

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_product_media_created(
    product_media_image, subscription_product_media_created_webhook
):
    media = product_media_image
    webhooks = [subscription_product_media_created_webhook]
    event_type = WebhookEventAsyncType.PRODUCT_MEDIA_CREATED
    media_id = graphene.Node.to_global_id("ProductMedia", media.id)
    deliveries = create_deliveries_for_subscriptions(event_type, media, webhooks)
    expected_payload = json.dumps(
        {
            "productMedia": {
                "id": media_id,
                "url": f"http://mirumee.com{media.image.url}",
                "productId": graphene.Node.to_global_id("Product", media.product_id),
            }
        }
    )

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) == len(webhooks)
    assert deliveries[0].webhook == webhooks[0]


def test_product_media_updated(
    product_media_image, subscription_product_media_updated_webhook
):
    media = product_media_image
    webhooks = [subscription_product_media_updated_webhook]
    event_type = WebhookEventAsyncType.PRODUCT_MEDIA_UPDATED
    media_id = graphene.Node.to_global_id("ProductMedia", media.id)
    deliveries = create_deliveries_for_subscriptions(event_type, media, webhooks)
    expected_payload = json.dumps(
        {
            "productMedia": {
                "id": media_id,
                "url": f"http://mirumee.com{media.image.url}",
                "productId": graphene.Node.to_global_id("Product", media.product_id),
            }
        }
    )

    assert deliveries[0].payload.payload == expected_payload
    assert len(deliveries) ==