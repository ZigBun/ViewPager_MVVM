import copy
import json
from unittest import mock

import freezegun
import graphene
import pytest
from freezegun import freeze_time

from ...order import OrderStatus
from ..event_types import WebhookEventAsyncType
from ..payloads import (
    generate_checkout_payload,
    generate_fulfillment_payload,
    generate_order_payload,
    generate_product_payload,
    generate_sample_payload,
)


def _remove_anonymized_order_data(order_data: dict) -> dict:
    order_data = copy.deepcopy(order_data)
    del order_data["id"]
    del order_data["user_email"]
    del order_data["billing_address"]
    del order_data["shipping_address"]
    del order_data["metadata"]
    del order_data["private_metadata"]
    return order_data


@freezegun.freeze_time("1914-06-28 10:50", ignore=["faker"])
@pytest.mark.parametrize(
    "event_name, order_status",
    [
        (WebhookEventAsyncType.ORDER_CREATED, OrderStatus.UNFULFILLED),
        (WebhookEventAsyncType.ORDER_UPDATED, OrderStatus.CANCELED),
        (WebhookEventAsyncType.ORDER_CANCELLED, OrderStatus.CANCELED),
        (WebhookEventAsyncType.ORDER_FULFILLED, OrderStatus.FULFILLED),
        (WebhookEventAsyncType.ORDER_FULLY_PAID, OrderStatus.FULFILLED),
    ],
)
def test_generate_sample_payload_order(
    event_name, order_status, fulfilled_order, payment_txn_captured
):
    order = fulfilled_order
    order.status = order_status
    order.save()
    order_id = graphene.Node.to_global_id("Order", order.id)
    payload = generate_sample_payload(event_name)
    order_payload = json.loads(generate_order_payload(order))
    # Check anonymized data differ
    assert order_id == payload[0]["id"]
    assert order.user_email != payload[0]["user_email"]
    assert (
        order.billing_address.street_address_1
        != payload[0]["billing_address"]["street_address_1"]
    )
    assert (
        order.shipping_address.street_address_1
        != payload[0]["shipping_address"]["street_address_1"]
    )
    assert order.metadata != payload[0]["metadata"]
    assert order.private_metadata != payload[0]["private_metadata"]
    # Remove anonymized data
    payload = _remove_anonymized_order_data(payload[0])
    order_payload = _remove_anonymized_order_data(order_payload[0])
    # Compare the payloads
    assert payload == order_payload


@freeze_time("1914-06-28 10:50", ignore=["faker"])
def test_generate_sample_payload_fulfillment_created(fulfillment):
    sample_fulfillment_payload = generate_sample_payload(
        WebhookEventAsyncType.FULFILLMENT_CREATED
    )[0]
    fulfillment_payload = json.loads(generate_fulfillment_payload(fulfillment))[0]
    order = fulfillment.order

    obj_id = graphene.Node.to_global_id("Fulfillment", fulfillment.id)
    order_id = graphene.Node.to_global_id("Order", order.id)

    assert obj_id == sample_fulfillment_payload["id"]
    # Check anonymized data differ
    assert order_id == sample_fulfillment_payload["order"]["id"]
    assert order.user_email != sample_fulfillment_payload["order"]["user_email"]
    assert (
        order.shipping_address.street_address_1
        != sample_fulfillment_payload["order"]["shipping_address"]["street_address_1"]
    )
    assert order.metadata != sample_fulfillment_payload["order"]["metadata"]
    assert (
        order.private_metadata
        != sample_fulfillment_payload["order"]["private_metadata"]
    )

    # Remove anonymized data
    sample_fulfillment_payload["order"] = _remove_anonymized_order_data(
        sample_fulfillment_payload["order"]
    )
    fulfillment_payload["order"] = _remove_anonymized_order_data(
        fulfillment_payload["order"]
    )
    # Compare the payloads
    assert sample_fulfillment_payload == fulfillment_payload


def test_generate_sample_payload_order_removed_channel_listing_from_shipping(
    fulfilled_order, payment_txn_captured
):
    # given
    event_name = WebhookEventAsyncType.ORDER_UPDATED
    order_status = OrderStatus.CANCELED
    order = fulfilled_order
    order.status = order_status
    order.shipping_method.channel_listings.all().delete()
    order.save()
    order_id = graphene.Node.to_global_id("Order", order.id)

    # when
    pa