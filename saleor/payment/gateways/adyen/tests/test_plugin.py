import json
from decimal import Decimal
from unittest import mock

import Adyen
import pytest
from django.core.exceptions import ValidationError
from requests.exceptions import ConnectTimeout, RequestException, SSLError

from .....plugins.models import PluginConfiguration
from .... import PaymentError, TransactionKind
from ....interface import GatewayResponse, PaymentMethodInfo
from ....models import Payment, Transaction
from ....utils import create_payment_information, create_transaction


@mock.patch("saleor.payment.gateways.adyen.plugin.api_call")
def test_process_additional_action(
    mocked_api_call,
    dummy_payment_data,
    payment_dummy,
    checkout_ready_to_complete,
    adyen_plugin,
):
    expected_message = {"resultCode": "authorised", "pspReference": "ref-id"}
    mocked_app_response = mock.MagicMock(message=expected_message)

    mocked_api_call.return_value = mocked_app_response
    plugin = adyen_plugin(auto_capture=False)
    dummy_payment_data.data = {
        "additional-data": "payment-data",
    }

    kind = TransactionKind.AUTH
    response = plugin._process_additional_action(dummy_payment_data, kind)

    assert response == GatewayResponse(
        is_success=True,
        action_required=False,
        action_required_data=None,
        kind=kind,
        amount=dummy_payment_data.amount,
        currency=dummy_payment_data.currency,
        transaction_id="ref-id",
        error=None,
        raw_response=expected_message,
        psp_reference="ref-id",
        payment_method_info=PaymentMethodInfo(),
    )
    mocked_api_call.assert_called_with(
        dummy_payment_data.data, plugin.adyen.checkout.payments_details
    )


@pytest.mark.vcr
def test_get_payment_gateway_for_checkout(
    adyen_plugin, checkout_with_single_item, address
):
    checkout_with_single_item.billing_address = address
    checkout_with_single_item.save()
    adyen_plugin = adyen_plugin()
    response = adyen_plugin.get_payment_gateways(
        currency=None, checkout=checkout_with_single_item, previous_value=None
    )[0]
    assert response.id == adyen_plugin.PLUGIN_ID
    assert response.name == adyen_plugin.PLUGIN_NAME
    config = response.config
    assert len(config) == 2
    assert config[0] == {
        "field": "client_key",
        "value": adyen_plugin.config.connection_params["client_key"],
    }
    assert config[1]["field"] == "config"
    config = json.loads(config[1]["value"])
    assert isinstance(config, dict)


@pytest.mark.vcr
def test_process_payment(
    payment_adyen_for_checkout, checkout_with_items, adyen_plugin, adyen_payment_method
):
    payment_info = create_payment_information(
        payment_adyen_for_checkout,
        additional_data={"paymentMethod": adyen_payment_method},
    )
    adyen_plugin = adyen_plugin()
    response = adyen_plugin.process_payment(payment_info, None)
    assert response.is_success is True
    assert response.action_required is False
    assert response.kind == TransactionKind.AUTH
    assert response.amount == Decimal("80.00")
    assert response.currency == checkout_with_items.currency
    assert response.transaction_id == "882609854544793A"  # ID returned by Adyen
    assert response.error is None
    assert response.action_required_data is None
    assert response.payment_method_info == PaymentMethodInfo(brand="visa", type="card")


@pytest.mark.vcr
@mock.patch("saleor.payment.gateways.adyen.plugin.call_capture")
def test_process_payment_with_adyen_auto_capture(
    capture_mock,
    payment_adyen_for_checkout,
    checkout_with_items,
    adyen_plugin,
    adyen_payment_method,
):
    payment_info = create_payment_information(
        payment_adyen_for_checkout,
        additional_data={"paymentMethod": adyen_payment_method},
    )
    adyen_plugin = adyen_plugin(adyen_auto_capture=True)
    response = adyen_plugin.process_payment(payment_info, None)
    # ensure call_capture is not called
    assert not capture_mock.called
    assert response.is_success is True
    assert response.action_required is False
    # kind should still be capture as Adyen had adyen_auto_capture set to True
    assert response.kind == TransactionKind.CAPTURE
    assert response.amount == Decimal("80.00")
    assert response.currency == checkout_with_items.currency
    assert response.transaction_id == "852610008487439C"  # ID returned by Adyen
    assert response.error is None


@pytest.mark.vcr
def test_process_payment_with_auto_capture(
    payment_adyen_for_checkout, checkout_with_items, adyen_plugin, adyen_payment_me