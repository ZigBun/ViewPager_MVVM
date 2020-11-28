from decimal import Decimal
from unittest.mock import patch

from stripe.error import AuthenticationError, StripeError
from stripe.stripe_object import StripeObject

from saleor.payment.interface import PaymentMethodInfo
from saleor.payment.utils import price_to_minor_unit

from ..consts import (
    AUTOMATIC_CAPTURE_METHOD,
    MANUAL_CAPTURE_METHOD,
    METADATA_IDENTIFIER,
    WEBHOOK_EVENTS,
)
from ..stripe_api import (
    cancel_payment_intent,
    capture_payment_intent,
    create_payment_intent,
    delete_webhook,
    get_or_create_customer,
    get_payment_method_details,
    is_secret_api_key_valid,
    list_customer_payment_methods,
    refund_payment_intent,
    retrieve_payment_intent,
    subscribe_webhook,
    update_payment_method,
)


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.WebhookEndpoint",
)
def test_is_secret_api_key_valid_incorrect_key(mocked_webhook):
    api_key = "incorrect"
    mocked_webhook.list.side_effect = AuthenticationError()
    assert is_secret_api_key_valid(api_key) is False


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.WebhookEndpoint",
)
def test_is_secret_api_key_valid_correct_key(mocked_webhook):
    api_key = "correct_key"
    assert is_secret_api_key_valid(api_key) is True

    mocked_webhook.list.assert_called_with(api_key)


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.WebhookEndpoint",
)
def test_subscribe_webhook_returns_webhook_object(mocked_webhook, channel_USD):
    api_key = "api_key"
    expected_url = (
        "http://mirumee.com/plugins/channel/main/saleor.payments.stripe/webhooks/"
    )

    subscribe_webhook(api_key, channel_slug=channel_USD.slug)

    mocked_webhook.create.assert_called_with(
        api_key=api_key,
        url=expected_url,
        enabled_events=WEBHOOK_EVENTS,
        metadata={METADATA_IDENTIFIER: "mirumee.com"},
    )


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.WebhookEndpoint",
)
def test_delete_webhook(mocked_webhook):
    api_key = "api_key"

    delete_webhook(api_key, "webhook_id")

    mocked_webhook.delete.assert_called_with(
        "webhook_id",
        api_key=api_key,
    )


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.PaymentIntent",
)
def test_create_payment_intent_returns_intent_object(mocked_payment_intent):
    api_key = "api_key"
    mocked_payment_intent.create.return_value = StripeObject()

    intent, error = create_payment_intent(
        api_key, Decimal(10), "USD", auto_capture=True
    )

    mocked_payment_intent.create.assert_called_with(
        api_key=api_key,
        amount="1000",
        currency="USD",
        capture_method=AUTOMATIC_CAPTURE_METHOD,
    )

    assert isinstance(intent, StripeObject)
    assert error is None


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.PaymentIntent",
)
def test_create_payment_intent_with_customer(mocked_payment_intent):
    customer = StripeObject(id="c_ABC")
    api_key = "api_key"
    mocked_payment_intent.create.return_value = StripeObject()

    intent, error = create_payment_intent(
        api_key, Decimal(10), "USD", auto_capture=True, customer=customer
    )

    mocked_payment_intent.create.assert_called_with(
        api_key=api_key,
        amount="1000",
        currency="USD",
        capture_method=AUTOMATIC_CAPTURE_METHOD,
        customer=customer,
    )

    assert isinstance(intent, StripeObject)
    assert error is None


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.PaymentIntent",
)
def test_create_payment_intent_manual_auto_capture(mocked_payment_intent):
    api_key = "api_key"
    mocked_payment_intent.create.return_value = StripeObject()

    _intent, _error = create_payment_intent(
        api_key, Decimal(10), "USD", auto_capture=False
    )

    mocked_payment_intent.create.assert_called_with(
        api_key=api_key,
        amount="1000",
        currency="USD",
        capture_method=MANUAL_CAPTURE_METHOD,
    )


@patch(
    "saleor.payment.gateways.stripe.stripe_api.stripe.PaymentIntent",
)
def test_create_payment_intent_returns_error(mocked_payment_intent):
    api_key = "api_key"
    mocked_payment_intent.create.side_effect = StripeError(
        json_body={"erro