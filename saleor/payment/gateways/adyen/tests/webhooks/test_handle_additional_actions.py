import json
import uuid
from decimal import Decimal
from unittest import mock
from urllib.parse import quote_plus

import graphene
import pytest

from ......order import OrderEvents
from ..... import PaymentError, TransactionKind
from ...webhooks import handle_additional_actions

ERROR_MSG_MISSING_PAYMENT = "Cannot perform payment. There is no active Adyen payment."
ERROR_MSG_MISSING_CHECKOUT = (
    "Cannot perform payment. There is no checkout with this payment."
)


@mock.patch("saleor.payment.gateways.adyen.webhooks.payment_refund_or_void")
@mock.patch("saleor.payment.gateways.adyen.webhooks.api_call")
def test_handle_additional_actions_post(
    api_call_mock, _, payment_adyen_for_checkout, adyen_plugin
):
    # given
    plugin = adyen_plugin()
    channel_slug = plugin.channel.slug
    payment_adyen_for_checkout.to_confirm = True
    payment_adyen_for_checkout.extra_data = json.dumps(
        [{"payment_data": "test_data", "parameters": ["payload"]}]
    )
    payment_adyen_for_checkout.save(update_fields=["to_confirm", "extra_data"])

    transaction_count = payment_adyen_for_checkout.transactions.all().count()

    checkout = payment_adyen_for_checkout.checkout
    payment_id = graphene.Node.to_global_id("Payment", payment_adyen_for_checkout.pk)
    checkout_id = graphene.Node.to_global_id("Checkout", checkout.pk)

    request_mock = mock.Mock()
    request_mock.GET = {"payment": payment_id, "checkout": str(checkout.pk)}
    request_mock.POST = {"payload": "test"}

    payment_details_mock = mock.Mock()
    message = {
        "pspReference": "11111",
        "resultCode": "Test",
    }
    api_call_mock.return_value.message = message

    # when
    response = handle_additional_actions(
        request_mock, payment_details_mock, channel_slug
    )

    # then
    payment_adyen_for_checkout.refresh_from_db()
    assert response.status_code == 302
    assert f"checkout={quote_plus(checkout_id)}" in response.url
    assert f"resultCode={message['resultCode']}" in response.url
    assert f"payment={quote_plus(payment_id)}" in response.url
    transactions = payment_adyen_for_checkout.transactions.all()
    assert transactions.count() == transaction_count + 2  # TO_CONFIRM, AUTH

    assert transactions.first().kind == TransactionKind.ACTION_TO_CONFIRM
    assert transactions.last().kind == TransactionKind.AUTH
    assert payment_adyen_for_checkout.order
    assert payment_adyen_for_checkout.checkout is None


@mock.patch("saleor.payment.gateways.adyen.webhooks.api_call")
def test_handle_additional_actions_order_already_created(
    api_call_mock, payment_adyen_for_order, adyen_plugin, order
):
    # given
    plugin = adyen_plugin()
    channel_slug = plugin.channel.slug
    payment_adyen_for_order.to_confirm = True
    payment_adyen_for_order.extra_data = json.dumps(
        [{"payment_data": "test_data", "parameters": ["payload"]}]
    )
    payment_adyen_for_order.save(update_fields=["to_confirm", "extra_data"])

    payment_id = graphene.Node.to_global_id("Payment", payment_adyen_for_order.pk)
    checkout_id = graphene.Node.to_global_id("Checkout", "1")

    request_mock = mock.Mock()
    request_mock.GET = {"payment": payment_id, "checkout": "1"}
    request_mock.POST = {"payload": "test"}

    payment_details_mock = mock.Mock()
    message = {
        "pspReference": "11111",
        "resultCode": "Test",
    }
    api_call_mock.return_value.message = message

    # when
    response = handle_additional_actions(
        request_mock, payment_details_mock, channel_slug
    )

    # then
    payment_adyen_for_order.refresh_from_db()
    assert response.status_code == 302
    assert f"checkout={quote_plus(checkout_id)}" in response.url
    assert f"resultCode={message['resultCode']}" in response.url
    assert f"payment={quote_plus(payment_id)}" in response.url

    assert payment_adyen_for_order.order
    assert payment_adyen_for_order.checkout is None


@pytest.mark.parametrize(
    "custom_url",
    [
        "adyencheckout://your.package.name",
        "myiOSapp://path",
        "https://checkout.saleor.com/",
    ],
)
@mock.patch("saleor.payment.gateways.adyen.webhooks.api_call")
def test_handle_additional_actions_handles_return_urls(
    api_call_mock, custom_url, payment_adyen_for_checkout, adyen_plugin
):
    # given
    plugin = adyen_plugin()
    channel_slug = plug