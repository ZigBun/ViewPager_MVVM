from decimal import Decimal
from unittest.mock import patch

import pytest
from razorpay.errors import BadRequestError, ServerError

from .... import ChargeStatus, TransactionKind
from ....interface import GatewayConfig
from ....utils import create_payment_information
from .. import (
    capture,
    check_payment_supported,
    clean_razorpay_response,
    errors,
    get_amount_for_razorpay,
    get_client,
    get_client_token,
    logger,
    refund,
)

TRANSACTION_AMOUNT = Decimal("61.33")


@pytest.fixture
def gateway_config():
    return GatewayConfig(
        gateway_name="razorpay",
        auto_capture=False,
        supported_currencies="USD",
        connection_params={
            "public_key": "public",
            "private_key": "secret",
            "prefill": True,
            "store_name": "Saleor",
            "store_image": "image.png",
        },
    )


@pytest.fixture()
def razorpay_success_response():
    return {
        "id": "transaction123",
        "amount": get_amount_for_razorpay(TRANSACTION_AMOUNT),
        "currency": "INR",
    }


@pytest.fixture()
def razorpay_payment(payment_dummy):
    payment_dummy.currency = "INR"
    return payment_dummy


@pytest.fixture()
def charged_payment(razorpay_payment):
    razorpay_payment.captured_amount = razorpay_payment.total
    razorpay_payment.charge_status = ChargeStatus.FULLY_CHARGED
    razorpay_payment.save(update_fields=["captured_amount", "charge_status"])

    razorpay_payment.transactions.create(
        amount=razorpay_payment.total,
        kind=TransactionKind.CAPTURE,
        gateway_response={},
        is_success=True,
    )
    return razorpay_payment


def test_check_payment_supported(razorpay_payment):
    payment_info = create_payment_information(razorpay_payment)
    found_error = check_payment_supported(payment_info)
    assert not found_error


def test_check_payment_supported_non_supported(razorpay_payment):
    razorpay_payment.currency = "USD"
    payment_info = create_payment_information(razorpay_payment)
    found_error = check_payment_supported(payment_info)
    assert found_error


def test_get_amount_for_razorpay():
    assert get_amount_for_razorpay(Decimal("61.33")) == 6133


def test_clean_razorpay_response():
    response = {"amount": 6133}
    clean_razorpay_response(response)
    assert response["amount"] == Decimal("61.33")


@patch("razorpay.Client")
def test_get_client(mocked_gateway, gateway_config):
    get_client(**gateway_config.connection_params)
    mocked_gateway.assert_called_once_with(auth=("public", "secret"))


def test_get_client_token():
    assert get_client_token()


@pytest.mark.integration
@patch("razorpay.Client")
def test_charge(
    mocked_gateway, razorpay_payment, razorpay_success_response, gateway_config
):
    # Data to be passed
    payment_token = "123"

    # Mock the gateway response to a success response
    mocked_gateway.return_value.payment.capture.return_value = razorpay_success_response

    payment_info = create_payment_information(
        razorpay_payment, payment_token=payment_token, amount=TRANSACTION_AMOUNT
    )

    # Attempt charging
    response = capture(payment_info, gateway_config)

    # Ensure the was no error returned
    assert not response.error
    assert response.is_success

    assert response.kind == TransactionKind.CAPTURE
    assert response.amount == TRANSACTION_AMOUNT
    assert respon