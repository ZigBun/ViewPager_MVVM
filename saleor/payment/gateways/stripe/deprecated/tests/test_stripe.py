import os
from decimal import Decimal
from math import isclose

import pytest

from ..... import ChargeStatus
from .....interface import CustomerSource, GatewayConfig, PaymentMethodInfo
from .....utils import create_payment_information
from .. import (
    TransactionKind,
    _get_client,
    authorize,
    capture,
    confirm,
    get_client_token,
    list_client_sources,
    refund,
    void,
)

TRANSACTION_AMOUNT = Decimal(42.42)
TRANSACTION_REFUND_AMOUNT = Decimal(24.24)
TRANSACTION_CURRENCY = "USD"
PAYMENT_METHOD_CARD_SIMPLE = "pm_card_pl"
CARD_SIMPLE_DETAILS = PaymentMethodInfo(
    last_4="0005", exp_year=2020, exp_month=8, brand="visa", type="card"
)
PAYMENT_METHOD_CARD_3D_SECURE = "pm_card_threeDSecure2Required"

# Set to True if recording new cassette with sandbox using credentials in env
RECORD = False


@pytest.fixture()
def gateway_config():
    return GatewayConfig(
        gateway_name="stripe",
        auto_capture=True,
        supported_currencies="USD",
        connection_params={
            "public_key": "public",
            "private_key": "secret",
            "store_name": "Saleor",
            "store_image": "image.gif",
            "prefill": True,
            "remember_me": True,
            "locale": "auto",
            "enable_billing_address": False,
            "enable_shipping_address": False,
        },
    )


@pytest.fixture()
def sandbox_gateway_config(gateway_config):
    if RECORD:
        connection_params = {
            "public_key": os.environ.get("STRIPE_PUBLIC_KEY"),
            "private_key": os.environ.get("STRIPE_SECRET_KEY"),
        }
        gateway_config.connection_params.update(connection_params)
    return gateway_config


@pytest.fixture()
def stripe_payment(payment_dummy):
    payment_dummy.total = TRANSACTION_AMOUNT
    payment_dummy.currency = TRANSACTION_CURRENCY
    return payment_dummy


@pytest.mark.integration
@pytest.mark.vcr(filter_headers=["authorization"])
def test_authorize(sandbox_gateway_config, stripe_payment):
    payment_info = create_payment_information(
        stripe_payment, PAYMENT_METHOD_CARD_SIMPLE
    )
    response = authorize(payment_info, sandbox_gateway_config)
    assert not response.error
    assert response.kind == TransactionKind.CAPTURE
    assert isclose(response.amount, TRANSACTION_AMOUNT)
    assert response.currency == TRANSACTION_CURRENCY
    assert response.is_success is True
    assert response.payment_method_info == CARD_SIMPLE_DETAILS
    assert not response.action_required


@pytest.mark.integration
@pytest.mark.vcr(filter_headers=["authorization"])
def test_authorize_error_response(stripe_payment, sandbox_gateway_config):
    INVALID_METHOD = "abcdefghijklmnoprstquwz"
    payment_info = create_payment_information(stripe_payment, INVALID_METHOD)
    response = authorize(payment_info, sandbox_gateway_config)

    assert response.error == "No such payment_method: " + INVALID_METHOD
    assert response.transaction_id == INVALID_METHOD
    assert response.kind == TransactionKind.CAPTURE
    assert not response.is_success
    assert response.amount == stripe_payment.total
    assert response.currency == stripe_payment.currency
    assert not response.action_required


@pytest.mark.integration
@pytest.mark.vcr(filter_headers=["authorization"])
def test_authorize_3d_secure(stripe_payment, sandbox_gateway_config):
    payment_info = create_payment_information(
        stripe_payment, PAYMENT_METHOD_CARD_3D_SECURE
    )
    response = authorize(payment_info, sandbox_gateway_config)
    assert not response.error
    assert response.kind == TransactionKind.CAPTURE
    assert isclose(response.amount, TRANSACTION_AMOUNT)
    assert response.currency == TRANSACTION_CURRENCY
    assert response.is_success is True
    assert response.action_required


@pytest.mark.integration
@pytest.mark.vcr(filter_headers=["authorization"])
def test_authorize_without_capture(stripe_payment, sandbox_gateway_config):
    sandbox_gateway_config.auto_capture = False
    payment_info = create_payment_information(
        stripe_payment, PAYMENT_METHOD_CARD_SIMPLE
    )
    response = authorize(payment_info, sandbox_gateway_config)
    assert not response.error
    assert response.kind == TransactionKind.AUTH
    assert isclose(response.amount, TRANSACTION_AMOUNT)
    assert response.currency == TRANSACTION_CURRENCY
    assert response.is_success is True


@pytest.mark.integration
@pytest.mark.vcr(filter_headers=["authorization"])
def test_authorize_and_save_customer_id(payment_dummy, sandbox_gateway_config):
    CUSTOMER_ID = "cus_FbquUfgBnLdlsY"  # retrieved from sandbox
    payment = payment_dummy

    payment_info = create_payment_information(payment, PAYMENT_METHOD_CARD_SIMPLE)

    sandbox_gateway_config.store_customer = True
    response = authorize(payment_info, sandbox_gateway_config)
    assert not response.error
    assert response.customer_id == CUSTOMER_ID


@pytest.mark.integration
@pytest.mark.vcr(filter_headers=["authorization"])
def test_authorize_with_customer_id(payment_dummy, sandbox_gateway_config):
    CUSTOMER_ID = "cus_FbquUfgBnLdlsY"  # retrieved from sandbox
    payment = payment_dummy

    payment_info = create_payment_information(payment, "pm_card_visa")
    payment_info.amount = TRANSACTION_AMOUNT
    payment_info.customer_id = CUSTOMER_ID
    payment_info.reuse_source = True

    response = authorize(payment_info, sandbox_gateway_config)
    assert not response.error
    assert response.is_success


@pytest.fixture()
def stripe_authorized_payment(stripe_payment):
    stripe_payment.charge_status = ChargeStatus.NOT_CHARGED
    stripe_payment.save(update_fields=["charge_status"])

    return stripe_payment


@pytest.mark.integration
@pytest.mark.vcr(filter_headers=["authorization"])
def test_capture(stripe_authorized_payment, sandbox_gateway_config):
    # Get id from sandbox for intent not yet captured
 