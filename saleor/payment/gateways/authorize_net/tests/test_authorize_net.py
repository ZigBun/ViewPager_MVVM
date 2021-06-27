import pytest

from .... import TransactionKind
from ....interface import PaymentData
from .. import (
    authenticate_test,
    capture,
    list_client_sources,
    process_payment,
    refund,
    void,
)

INVALID_TOKEN = "Y29kZTo1MF8yXzA2MDAwIHRva2VuOjEgdjoxLjE="
SUCCESS_TRANSACTION_ID = "60156217587"
REFUND_AMOUNT = 10.0
REFUND_TOKEN = "test"


@pytest.mark.integration
@pytest.mark.vcr()
def test_authenticate_test():
    success, _ = authenticate_test("test", "test", True)
    assert success


@pytest.mark.integration
@pytest.mark.vcr()
def test_authenticate_test_failure():
    success, message = authenticate_test("test", "test", True)
    assert not success
    assert message == "User authentication failed due to invalid authentication values."


@pytest.mark.integration
@pytest.mark.vcr()
def test_process_payment(dummy_payment_data, authorize_net_gateway_config):
    dummy_payment_data.token = INVALID_TOKEN
    response = process_payment(dummy_payment_data, authorize_net_gateway_config)
    assert not response.error
    assert response.transaction_id == SUCCESS_TRANSACTION_ID
    assert response.kind == TransactionKind.CAPTURE
    assert response.is_success
    assert response.amount == dummy_payment_data.amount
    assert response.currency == dummy_payment_data.currency
    assert not response.action_required


@pytest.mark.integration
@pytest.mark.vcr()
def test_process_payment_with_user(
    dummy_payment_data, authorize_net_gateway_config, address
):
    dummy_payment_data.token = INVALID_TOKEN
    dummy_payment_data.billing = address
    user_id = 123
    response = process_payment(
        dummy_payment_data, authorize_net_gateway_config, user_id
    )
    assert not response.error
    assert response.kind == TransactionKind.CAPTURE
    assert response.is_success
    assert response.amount == dummy_payment_data.amount
    assert response.currency == dummy_payment_data.currency


@pytest.mark.integration
@pytest.mark.vcr()
def test_process_payment_reuse_source(dummy_payment_data, authorize_net_gateway_config):
    dummy_payment_data.token = INVALID_TOKEN
    dummy_payment_data.reuse_source = True
    user_id = 124
    response = process_payment(
        dummy_payment_data, authorize_net_gateway_config, user_id
    )
    assert not response.error
    assert response.kind == TransactionKind.CAPTURE
    assert response.is_success
    assert response.customer_id == 1929153842


@pytest.mark.integration
@pytest.mark.vcr()
def test_process