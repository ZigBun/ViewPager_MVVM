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
    checkout.save()
    checkout.metadata_storage.save()

    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    delivery_method_info = checkout_info.delivery_method_info

    assert delivery_method_info.is_method_in_valid_methods(checkout_info)


@patch("saleor.plugins.webhook.tasks.send_webhook_request_sync")
def test_is_valid_delivery_method_external_method_no_longer_available(
    mock_send_request, checkout_with_item, address, settings, shipping_app
):
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]
    mock_json_response = [
        {
            "id": "New-ID",
            "name": "Provider - Economy",
            "amount": "10",
            "currency": "USD",
            "maximum_delivery_days": "7",
        }
    ]
    method_id = graphene.Node.to_global_id("app", f"{shipping_app.id}:1")

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

    assert delivery_method_info.is_method_in_valid_methods(checkout_info) is False


def test_clear_delivery_method(checkout, shipping_method):
    checkout.shipping_method = shipping_method
    checkout.save()
    manager = get_plugins_manager()
    checkout_info = fetch_checkout_info(checkout, [], [], manager)
    clear_delivery_method(checkout_info)
    checkout.refresh_from_db()
    assert not checkout.shipping_method
    assert isinstance(checkout_info.delivery_method_info, DeliveryMethodBase)


def test_last_change_update(checkout):
    with freeze_time(datetime.datetime.now()) as frozen_datetime:
        assert checkout.last_change != frozen_datetime()

        checkout.note = "Sample note"
        checkout.save()

        assert checkout.last_change == pytz.utc.localize(frozen_datetime())


def test_last_change_update_foreign_key(checkout, shipping_method):
    with freeze_time(datetime.datetime.now()) as frozen_datetime:
        assert checkout.last_change != frozen_datetime()

        checkout.shipping_method = shipping_method
        checkout.save(update_fields=["shipping_method", "last_change"])

        assert checkout.last_change == pytz.utc.localize(frozen_datetime())


@pytest.mark.parametrize(
    "total, min_spent_amount, min_checkout_items_quantity, once_per_order, "
    "discount_value, discount_value_type, expected_value",
    [
        (20, 20, 2, False, 50, DiscountValueType.PERCENTAGE, Decimal("10.00")),
        (20, None, None, False, 50, DiscountValueType.PERCENTAGE, Decimal("10.00")),
        (20, 20, 2, False, 5, DiscountValueType.FIXED, Decimal("5.00")),
        (20, None, None, False, 5, DiscountValueType.FIXED, Decimal("5.00")),
        (20, 20, 2, True, 50, DiscountValueType.PERCENTAGE, Decimal("5.00")),
        (20, None, None, True, 50, DiscountValueType.PERCENTAGE, Decimal("5.00")),
        (20, 20, 2, True, 5, DiscountValueType.FIXED, Decimal("5.00")),
        (20, None, None, True, 5, DiscountValueType.FIXED, Decimal("5.00")),
    ],
)
def test_get_discount_for_checkout_value_entire_order_voucher(
    total,
    min_spent_amount,
    min_checkout_items_quantity,
    once_per_order,
    discount_value,
    discount_value_type,
    expected_value,
    monkeypatch,
    channel_USD,
    checkout_with_items,
):
    # given
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.ENTIRE_ORDER,
        discount_value_type=discount_value_type,
        min_checkout_items_quantity=min_checkout_items_quantity,
        apply_once_per_order=once_per_order,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(discount_value, channel_USD.currency_code),
        min_spent_amount=(min_spent_amount if min_spent_amount is not None else None),
    )
    checkout = Mock(spec=checkout_with_items, channel=channel_USD)
    subtotal = Money(total, "USD")
    monkeypatch.setattr(
        "saleor.checkout.base_calculations.base_checkout_subtotal",
        lambda *args: subtotal,
    )
    checkout_info = CheckoutInfo(
        checkout=checkout,
        shipping_address=None,
        billing_address=None,
        channel=channel_USD,
        user=None,
        tax_configuration=channel_USD.tax_configuration,
        valid_pick_up_points=[],
        delivery_method_info=get_delivery_method_info(None, None),
        all_shipping_methods=[],
    )
    lines = [
        CheckoutLineInfo(
            line=line,
            channel_listing=line.variant.channel_listings.first(),
            collections=[],
            product=line.variant.product,
            variant=line.variant,
            product_type=line.variant.product.product_type,
        )
        for line in checkout_with_items.lines.all()
    ]
    manager = get_plugins_manager()

    # when
    discount = get_voucher_discount_for_checkout(
        manager, voucher, checkout_info, lines, None, []
    )

    # then
    assert discount == Money(expected_value, "USD")


@pytest.mark.parametrize(
    "prices, min_spent_amount, min_checkout_items_quantity, once_per_order, "
    "discount_value, discount_value_type, expected_value",
    [
        (
            [Money(10, "USD"), Money(20, "USD")],
            20,
            2,
            False,
            50,
            DiscountValueType.PERCENTAGE,
            Decimal("15.00"),
        ),
        (
            [Money(10, "USD"), Money(20, "USD")],
            None,
            None,
            False,
            50,
            DiscountValueType.PERCENTAGE,
            Decimal("15.00"),
        ),
        (
            [Money(10, "USD"), Money(20, "USD")],
            20,
            2,
            False,
            5,
            DiscountValueType.FIXED,
            Decimal("10.00"),
        ),
        (
            [Money(10, "USD"), Money(20, "USD")],
            None,
            None,
            False,
            5,
            DiscountValueType.FIXED,
            Decimal("10.00"),
        ),
        (
            [Money(10, "USD"), Money(20, "USD")],
            20,
            2,
            True,
            50,
            DiscountValueType.PERCENTAGE,
            Decimal("5.00"),
        ),
        (
            [Money(10, "USD"), Money(20, "USD")],
            None,
            None,
            True,
            50,
            DiscountValueType.PERCENTAGE,
            Decimal("5.00"),
        ),
        (
            [Money(10, "USD"), Money(20, "USD")],
            20,
            2,
            True,
            5,
            DiscountValueType.FIXED,
            Decimal("5.00"),
        ),
        (
            [Money(10, "USD"), Money(20, "USD")],
            None,
            None,
            True,
            5,
            DiscountValueType.FIXED,
            Decimal("5.00"),
        ),
    ],
)
def test_get_discount_for_checkout_value_specific_product_voucher(
    prices,
    min_spent_amount,
    min_checkout_items_quantity,
    once_per_order,
    discount_value,
    discount_value_type,
    expected_value,
    monkeypatch,
    channel_USD,
    checkout_with_items,
):
    # given
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SPECIFIC_PRODUCT,
        discount_value_type=discount_value_type,
        min_checkout_items_quantity=min_checkout_items_quantity,
        apply_once_per_order=once_per_order,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(discount_value, channel_USD.currency_code),
        min_spent_amount=(min_spent_amount if min_spent_amount is not None else None),
    )
    variants = [line.variant for line in checkout_with_items.lines.all()]
    voucher.variants.add(*variants)

    checkout = Mock(spec=checkout_with_items, channel=channel_USD)
    monkeypatch.setattr(
        "saleor.checkout.utils.get_base_lines_prices",
        Mock(return_value=prices),
    )
    subtotal = sum(prices, start=Money(0, "USD"))
    monkeypatch.setattr(
        "saleor.checkout.base_calculations.base_checkout_subtotal",
        lambda *args: subtotal,
    )
    checkout_info = CheckoutInfo(
        checkout=checkout,
        shipping_address=None,
        billing_address=None,
        channel=channel_USD,
        user=None,
        tax_configuration=channel_USD.tax_configuration,
        valid_pick_up_points=[],
        delivery_method_info=get_delivery_method_info(None, None),
        all_shipping_methods=[],
    )
    lines = [
        CheckoutLineInfo(
            line=line,
            channel_listing=line.variant.channel_listings.first(),
            collections=[],
            product=line.variant.product,
            variant=line.variant,
            product_type=line.variant.product.product_type,
        )
        for line in checkout_with_items.lines.all()
    ]
    manager = get_plugins_manager()

    # when
    discount = get_voucher_discount_for_checkout(
        manager, voucher, checkout_info, lines, None, []
    )

    # then
    assert discount == Money(expected_value, "USD")


@patch("saleor.discount.utils.validate_voucher")
def test_get_voucher_discount_for_checkout_voucher_validation(
    mock_validate_voucher, voucher, checkout_with_voucher
):
    # given
    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout_with_voucher)
    quantity = calculate_checkout_quantity(lines)
    checkout_info = fetch_checkout_info(checkout_with_voucher, lines, [], manager)
    manager = get_plugins_manager()
    address = checkout_with_voucher.shipping_address

    # when
    get_voucher_discount_for_checkout(manager, voucher, checkout_info, lines, address)

    # then
    subtotal = base_calculations.base_checkout_subtotal(
        lines, checkout_info.channel, checkout_with_voucher.currency, []
    )
    customer_email = checkout_with_voucher.get_customer_email()
    mock_validate_voucher.assert_called_once_with(
        voucher,
        subtotal,
        quantity,
        customer_email,
        checkout_with_voucher.channel,
        checkout_info.user,
    )


@pytest.mark.parametrize(
    "total, total_quantity, discount_value, discount_type, min_spent_amount, "
    "min_checkout_items_quantity",
    [
        ("99", 9, 10, DiscountValueType.FIXED, None, 10),
        ("99", 9, 10, DiscountValueType.FIXED, 100, None),
        ("99", 10, 10, DiscountValueType.PERCENTAGE, 100, 10),
        ("100", 9, 10, DiscountValueType.PERCENTAGE, 100, 10),
        ("99", 9, 10, DiscountValueType.PERCENTAGE, 100, 10),
    ],
)
def test_get_discount_for_checkout_entire_order_voucher_not_applicable(
    total,
    total_quantity,
    discount_value,
    discount_type,
    min_spent_amount,
    min_checkout_items_quantity,
    monkeypatch,
    channel_USD,
):
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.ENTIRE_ORDER,
        discount_value_type=discount_type,
        min_checkout_items_quantity=min_checkout_items_quantity,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(discount_value, channel_USD.currency_code),
        min_spent_amount=(min_spent_amount if min_spent_amount is not None else None),
    )
    checkout = Mock(spec=Checkout, channel=channel_USD)
    subtotal = Money(total, "USD")
    monkeypatch.setattr(
        "saleor.checkout.base_calculations.base_checkout_subtotal",
        lambda *args: subtotal,
    )
    checkout_info = CheckoutInfo(
        checkout=checkout,
        delivery_method_info=None,
        shipping_address=None,
        billing_address=None,
        channel=channel_USD,
        user=None,
        tax_configuration=channel_USD.tax_configuration,
        valid_pick_up_points=[],
        all_shipping_methods=[],
    )
    manager = get_plugins_manager()
    with pytest.raises(NotApplicable):
        get_voucher_discount_for_checkout(manager, voucher, checkout_info, [], None, [])


@pytest.mark.parametrize(
    "discount_value, discount_type, total_discount_amount",
    [
        (5, DiscountValueType.FIXED, Decimal("15.00")),
        (10, DiscountValueType.PERCENTAGE, Decimal("6.00")),
    ],
)
def test_get_discount_for_checkout_specific_products_voucher(
    priced_checkout_with_items,
    product_list,
    discount_value,
    discount_type,
    total_discount_amount,
    channel_USD,
):
    # given
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SPECIFIC_PRODUCT,
        discount_value_type=discount_type,
        apply_once_per_order=False,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(discount_value, channel_USD.currency_code),
    )
    for product in product_list:
        voucher.products.add(product)
    priced_checkout_with_items.voucher_code = voucher.code
    priced_checkout_with_items.save()
    manager = get_plugins_manager()

    # when
    lines, _ = fetch_checkout_lines(priced_checkout_with_items)
    checkout_info = fetch_checkout_info(priced_checkout_with_items, lines, [], manager)
    subtotal = manager.calculate_checkout_subtotal(
        checkout_info, lines, checkout_info.shipping_address, []
    ).gross

    # then
    for line in lines:
        line.voucher = None
    subtotal_without_voucher = manager.calculate_checkout_subtotal(
        checkout_info, lines, checkout_info.shipping_address, []
    )

    currency = checkout_info.checkout.currency
    expected_subtotal = subtotal_without_voucher.gross - Money(
        total_discount_amount, currency
    )
    assert expected_subtotal == subtotal


@pytest.mark.parametrize(
    "discount_value, discount_type, total_discount_amount",
    [
        (5, DiscountValueType.FIXED, 5),
        (10000, DiscountValueType.FIXED, 10),
        (10, DiscountValueType.PERCENTAGE, 1),
    ],
)
def test_get_discount_for_checkout_specific_products_voucher_apply_only_once(
    checkout_with_items,
    product_list,
    discount_value,
    discount_type,
    total_discount_amount,
    channel_USD,
):
    # given
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SPECIFIC_PRODUCT,
        discount_value_type=discount_type,
        apply_once_per_order=True,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(discount_value, channel_USD.currency_code),
    )
    for product in product_list:
        voucher.products.add(product)
    checkout_with_items.voucher_code = voucher.code
    checkout_with_items.save()
    manager = get_plugins_manager()

    # when
    lines, _ = fetch_checkout_lines(checkout_with_items)
    checkout_info = fetch_checkout_info(checkout_with_items, lines, [], manager)
    subtotal = manager.calculate_checkout_subtotal(
        checkout_info, lines, checkout_info.shipping_address, []
    ).gross

    # then
    assert [line.voucher is not None for line in lines].count(True) == 1

    for line in lines:
        line.voucher = None
    subtotal_without_voucher = manager.calculate_checkout_subtotal(
        checkout_info, lines, checkout_info.shipping_address, []
    )

    assert subtotal == subtotal_without_voucher.gross - Money(
        total_discount_amount, checkout_info.checkout.currency
    )


@pytest.mark.parametrize(
    "total, total_quantity, discount_value, discount_type, min_spent_amount,"
    "min_checkout_items_quantity",
    [
        ("99", 9, 10, DiscountValueType.FIXED, None, 10),
        ("99", 9, 10, DiscountValueType.FIXED, 100, None),
        ("99", 10, 10, DiscountValueType.PERCENTAGE, 100, 10),
        ("100", 9, 10, DiscountValueType.PERCENTAGE, 100, 10),
        ("99", 9, 10, DiscountValueType.PERCENTAGE, 100, 10),
    ],
)
def test_get_discount_for_checkout_specific_products_voucher_not_applicable(
    monkeypatch,
    total,
    total_quantity,
    discount_value,
    discount_type,
    min_spent_amount,
    min_checkout_items_quantity,
    channel_USD,
):
    discounts = []
    monkeypatch.setattr(
        "saleor.checkout.utils.get_prices_of_discounted_specific_product",
        lambda checkout, discounts, product: [],
    )
    monkeypatch.setattr(
        "saleor.checkout.calculations.checkout_shipping_price",
        lambda _: TaxedMoney(Money(0, "USD"), Money(0, "USD")),
    )
    monkeypatch.setattr(
        "saleor.checkout.base_calculations.base_checkout_subtotal",
        lambda *args: Money(total, "USD"),
    )

    manager = get_plugins_manager()
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SPECIFIC_PRODUCT,
        discount_value_type=discount_type,
        min_checkout_items_quantity=min_checkout_items_quantity,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(discount_value, channel_USD.currency_code),
        min_spent_amount=(min_spent_amount if min_spent_amount is not None else None),
    )
    checkout = Mock(quantity=total_quantity, spec=Checkout, channel=channel_USD)
    checkout_info = CheckoutInfo(
        checkout=checkout,
        delivery_method_info=get_delivery_method_info(None, None),
        shipping_address=None,
        billing_address=None,
        channel=channel_USD,
        user=None,
        tax_configuration=channel_USD.tax_configuration,
        valid_pick_up_points=[],
        all_shipping_methods=[],
    )
    with pytest.raises(NotApplicable):
        get_voucher_discount_for_checkout(
            manager, voucher, checkout_info, [], None, discounts
        )


@pytest.mark.parametrize(
    "shipping_cost, shipping_country_code, discount_value, discount_type,"
    "countries, expected_value",
    [
        (
            Decimal("10.00"),
            None,
            50,
            DiscountValueType.PERCENTAGE,
            [],
            Decimal("5.00"),
        ),
        (
            Decimal("10.00"),
            None,
            20,
            DiscountValueType.FIXED,
            [],
            Decimal("10.00"),
        ),
        (
            Decimal("10.00"),
            "PL",
            20,
            DiscountValueType.FIXED,
            [],
            Decimal("10.00"),
        ),
        (
            Decimal("5.00"),
            "PL",
            Decimal("5.00"),
            DiscountValueType.FIXED,
            ["PL"],
            Decimal("5.00"),
        ),
        (
            Decimal("5.00"),
            "PL",
            Decimal("5.00"),
            DiscountValueType.FIXED,
            ["PL"],
            Decimal("5.00"),
        ),
    ],
)
def test_get_discount_for_checkout_shipping_voucher(
    shipping_cost,
    shipping_country_code,
    discount_value,
    discount_type,
    countries,
    expected_value,
    monkeypatch,
    channel_USD,
    shipping_method,
    shipping_method_data,
):
    manager = get_plugins_manager()
    tax = Decimal("1.23")
    shipping = TaxedMoney(
        Money(shipping_cost, "USD"), Money(shipping_cost * tax, "USD")
    )
    subtotal = Money(100, "USD")
    monkeypatch.setattr(
        "saleor.checkout.base_calculations.base_checkout_subtotal",
        lambda *args: subtotal,
    )
    monkeypatch.setattr(
        "saleor.checkout.utils.is_shipping_required", lambda lines: True
    )
    checkout = Mock(
        spec=Checkout,
        is_shipping_required=Mock(return_value=True),
        channel_id=channel_USD.id,
        channel=channel_USD,
        shipping_method=shipping_method,
        get_shipping_price=Mock(return_value=shipping.gross),
        shipping_address=Mock(country=Country(shipping_country_code)),
    )
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SHIPPING,
        discount_value_type=discount_type,
        countries=countries,
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(discount_value, channel_USD.currency_code),
    )
    shipping_address = Mock(spec=Address, country=Mock(code="PL"))
    checkout_info = CheckoutInfo(
        checkout=checkout,
        shipping_address=shipping_address,
        delivery_method_info=get_delivery_method_info(
            shipping_method_data, shipping_address
        ),
        billing_address=None,
        channel=channel_USD,
        user=None,
        tax_configuration=channel_USD.tax_configuration,
        valid_pick_up_points=[],
        all_shipping_methods=[],
    )

    discount = get_voucher_discount_for_checkout(
        manager, voucher, checkout_info, [], None, None
    )
    assert discount == Money(expected_value, "USD")


def test_get_discount_for_checkout_shipping_voucher_all_countries(
    monkeypatch, channel_USD, shipping_method, shipping_method_data
):
    subtotal = Money(100, "USD")
    monkeypatch.setattr(
        "saleor.checkout.base_calculations.base_checkout_subtotal",
        lambda *args: subtotal,
    )
    monkeypatch.setattr(
        "saleor.checkout.utils.is_shipping_required", lambda lines: True
    )
    shipping_total = TaxedMoney(Money(10, "USD"), Money(10, "USD"))
    checkout = Mock(
        spec=Checkout,
        channel_id=channel_USD.id,
        channel=channel_USD,
        shipping_method_id=shipping_method.id,
        is_shipping_required=Mock(return_value=True),
        shipping_method=Mock(get_total=Mock(return_value=shipping_total)),
        shipping_address=Mock(country=Country("PL")),
    )
    voucher = Voucher.objects.create(
        code="unique",
        type=VoucherType.SHIPPING,
        discount_value_type=DiscountValueType.PERCENTAGE,
        countries=[],
    )
    VoucherChannelListing.objects.create(
        voucher=voucher,
        channel=channel_USD,
        discount=Money(50, channel_USD.currency_code),
    )

    manager = get_plugins_manager()
    checkout_info = CheckoutInfo(
        checkout=checkout,
        delivery_method_info=get_delivery_method_info(shipping_method_data),
        shipping_address=Mock(spec=Address, country=Mock(code="PL")),
        billing_address=None,
        channel=channel_USD,
        user=None,
        tax_configuration=channel_USD.tax_configuration,
        valid_pick_up_points=[],
        all_shipping_methods=[],
    )
    discount = get_voucher_discount_for_checkout(
        manager, voucher, checkout_info, [], None, None
    )

    assert discount 