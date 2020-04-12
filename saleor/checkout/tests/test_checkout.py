import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import graphene
import pytest
import pytz
from django.utils import timezone
from django_countries.fields import Country
from freezegun import freeze_time
from prices import Money, TaxedMoney

from ...account.models import Address
from ...core.taxes import zero_money
from ...discount import DiscountValueType, VoucherType
from ...discount.models import NotApplicable, Voucher, VoucherChannelListing
from ...payment.models import Payment
from ...plugins.manager import get_plugins_manager
from ...shipping.interface import ShippingMethodData
from ...shipping.models import ShippingZone
from .. import base_calculations, calculations
from ..fetch import (
    CheckoutInfo,
    CheckoutLineInfo,
    DeliveryMethodBase,
    fetch_checkout_info,
    fetch_checkout_lines,
    get_delivery_method_info,
)
from ..models import Checkout, CheckoutLine
from ..utils import (
    PRIVATE_META_APP_SHIPPING_ID,
    add_voucher_to_checkout,
    calculate_checkout_quantity,
    cancel_active_payments,
    change_billing_address_in_checkout,
    change_shipping_address_in_checkout,
    clear_delivery_method,
    delete_external_shipping_id,
    get_external_shipping_id,
    get_voucher_discount_for_checkout,
    get_voucher_for_checkout_info,
    is_fully_paid,
    recalculate_checkout_discount,
    remove_voucher_from_checkout,
    set_external_shipping_id,
)


def test_is_valid_delivery_method(checkout_with_item, address, shipping_zone):
    checkout = checkout_with_item
    checkout.shipping_address = address
    checkout.save()
    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    delivery_method_info = checkout_info.delivery_method_info
    # no shipping method assigned
    assert not delivery_method_info.is_valid_delivery_method()
    shipping_method = shipping_zone.shipping_methods.first()
    checkout.shipping_method = shipping_method
    checkout.save()
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    delivery_method_info = checkout_info.delivery_method_info

    assert delivery_method_info.is_valid_delivery_method()

    zone = ShippingZone.objects.create(name="DE", countries=["DE"])
    shipping_method.shipping_zone = zone
    shipping_method.save()
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    delivery_method_info = checkout_info.delivery_method_info

    assert not delivery_method_info.is_method_in_valid_methods(checkout_info)


@patch("saleor.plugins.webhook.tasks.send_webhook_request_sync")
def test_is_valid_delivery_method_external_method(
    mock_send_request, checkout_with_item, address, settings, shipping_app
):
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]
    assert not shipping_app.identifier
    response_method_id = "abcd"
    mock_json_response = [
        {
            "id": response_method_id,
            "name": "Provider - Economy",
            "amount": "10",
            "currency": "USD",
            "maximum_delivery_days": "7",
        }
    ]
    method_id = graphene.Node.to_global_id(
        "app", f"{shipping_app.id}:{response_method_id}"
    )

    mock_send_request.return_value = mock_json_response
    checkout = checkout_with_item
    checkout.shipping_address = address
    checkout.metadata_storage.private_metadata = {
        PRIVATE_META_APP_SHIPPING_ID: method_id
    }
    checkout.save()
    checkout.metadata_storage.save()

    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    delivery_method_info = checkout_info.delivery_method_info

    assert delivery_method_info.is_method_in_valid_methods(checkout_info)


@patch("saleor.plugins.webhook.tasks.send_webhook_request_sync")
def test_is_valid_delivery_method_external_method_shipping_app_id_with_identifier(
    mock_send_request, checkout_with_item, address, settings, shipping_app
):
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    shipping_app.identifier = "abcd"
    shipping_app.save(update_fields=["identifier"])

    response_method_id = "123"
    mock_json_response = [
        {
            "id": response_method_id,
            "name": "Provider - Economy",
            "amount": "10",
            "currency": "USD",
            "maximum_delivery_days": "7",
        }
    ]
    method_id = graphene.Node.to_global_id(
        "app", f"{shipping_app.identifier}:{response_method_id}"
    )

    mock_send_request.return_value = mock_json_response
    checkout = checkout_with_item
    checkout.shipping_address = address
    checkout.metadata_storage.private_metadata = {
        PRIVATE_META_APP_SHIPPING_ID: method_id
    }
    checkout.save()
    checkout.metadata_storage.save()

    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    delivery_method_info = checkout_info.delivery_method_info

    assert delivery_method_info.is_method_in_valid_methods(checkout_info)


@patch("saleor.plugins.webhook.tasks.send_webhook_request_sync")
def test_is_valid_delivery_method_external_method_old_shipping_app_id(
    mock_send_request, checkout_with_item, address, settings, shipping_app
):
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    shipping_app.identifier = "abcd"
    shipping_app.save(update_fields=["identifier"])

    response_method_id = "123"
    mock_json_response = [
        {
            "id": response_method_id,
            "name": "Provider - Economy",
            "amount": "10",
            "currency": "USD",
            "maximum_delivery_days": "7",
        }
    ]
    method_id = graphene.Node.to_global_id(
        "app", f"{shipping_app.id}:{response_method_id}"
    )

    mock_send_request.return_value = mock_json_response
    checkout = checkout_with_item
    checkout.shipping_address = address
    checkout.metadata_storage.private_metadata = {
        PRIVATE_META_APP_SHIPPING_ID: method_id
    }
    checkout.sav