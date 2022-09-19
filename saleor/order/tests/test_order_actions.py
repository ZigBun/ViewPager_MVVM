from decimal import Decimal
from unittest.mock import patch

import pytest
from prices import Money, TaxedMoney

from ...giftcard import GiftCardEvents
from ...giftcard.models import GiftCard, GiftCardEvent
from ...order.fetch import OrderLineInfo, fetch_order_info
from ...payment import ChargeStatus, PaymentError, TransactionKind
from ...payment.models import Payment
from ...plugins.manager import get_plugins_manager
from ...product.models import DigitalContent
from ...product.tests.utils import create_image
from ...tests.utils import flush_post_commit_hooks
from ...warehouse.models import Allocation, Stock
from .. import FulfillmentStatus, OrderEvents, OrderStatus
from ..actions import (
    automatically_fulfill_digital_lines,
    cancel_fulfillment,
    cancel_order,
    clean_mark_order_as_paid,
    fulfill_order_lines,
    handle_fully_paid_order,
    mark_order_as_paid,
    order_refunded,
)
from ..models import Fulfillment, OrderLine
from ..notifications import (
    send_fulfillment_confirmation_to_customer,
    send_payment_confirmation,
)


@pytest.fixture
def order_with_digital_line(order, digital_content, stock, site_settings):
    site_settings.automatic_fulfillment_digital_products = True
    site_settings.save()

    variant = stock.product_variant
    variant.digital_content = digital_content
    variant.digital_content.save()

    product_type = variant.product.product_type
    product_type.is_shipping_required = False
    product_type.is_digital = True
    product_type.save()

    quantity = 3
    product = variant.product
    channel = order.channel
    variant_channel_listing = variant.channel_listings.get(channel=channel)
    net = variant.get_price(product, [], channel, variant_channel_listing, None)
    gross = Money(amount=net.amount * Decimal(1.23), currency=net.currency)
    unit_price = TaxedMoney(net=net, gross=gross)
    line = order.lines.create(
        product_name=str(product),
        variant_name=str(variant),
        product_sku=variant.sku,
        product_variant_id=variant.get_global_id(),
        is_shipping_required=variant.is_shipping_required(),
        is_gift_card=variant.is_gift_card(),
        quantity=quantity,
        variant=variant,
        unit_price=unit_price,
        total_price=unit_price * quantity,
        tax_rate=Decimal("0.23"),
    )

    Allocation.objects.create(order_line=line, stock=stock, quantity_allocated=quantity)

    return order


@patch(
    "saleor.order.actions.send_fulfillment_confirmation_to_customer",
    wraps=send_fulfillment_confirmation_to_customer,
)
@patch(
    "saleor.order.actions.send_payment_confirmation", wraps=send_payment_confirmation
)
def test_handle_fully_paid_order_digital_lines(
    mock_send_payment_confirmation,
    send_fulfillment_confirmation_to_customer,
    order_with_digital_line,
):
    order = order_with_digital_line
    order.payments.add(Payment.objects.create())
    redirect_url = "http://localhost.pl"
    order = order_with_digital_line
    order.redirect_url = redirect_url
    order.save()
    order_info = fetch_order_info(order)
    manager = get_plugins_manager()

    handle_fully_paid_order(manager, order_info)

    fulfillment = order.fulfillments.first()
    event_order_paid = order.events.get()

    assert event_order_paid.type == OrderEvents.ORDER_FULLY_PAID

    mock_send_payment_confirmation.assert_called_once_with(order_info, manager)
    send_fulfillment_confirmation_to_customer.assert_called_once_with(
        order, fulfillment, user=order.user, app=None, manager=manager
    )

    order.refresh_from_db()
    assert order.status == OrderStatus.FULFILLED


@patch("saleor.order.actions.send_payment_confirmation")
def test_handle_fully_paid_order(mock_send_payment_confirmation, order):
    manager = get_plugins_manager()

    order.payments.add(Payment.objects.create())
    order_info = fetch_order_info(order)

    handle_fully_paid_order(manager, order_info)

    event_order_paid = order.events.get()
    assert event_order_paid.type == OrderEvents.ORDER_FULLY_PAID

    mock_send_payment_confirmation.assert_called_once_with(order_info, manager)


@patch("saleor.order.notifications.send_payment_confirmation")
def test_handle_fully_paid_order_no_email(mock_send_payment_confirmation, order):
    order.user = None
    order.user_email = ""
    manager = get_plugins_manager()
    order_info = fetch_order_info(order)

    handle_fully_paid_order(manager, order_info)
    event = order.events.get()
    assert event.type == OrderEvents.ORDER_FULLY_PAID
    assert not mock_send_payment_confirmation.called


@patch("saleor.giftcard.utils.send_gift_card_notification")
@patch("saleor.order.actions.send_payment_confirmation")
def test_handle_fully_paid_order_gift_cards_created(
    mock_send_payment_confirmation,
    send_notification_mock,
    site_settings,
    order_with_lines,
    non_shippable_gift_card_product,
    shippable_gift_card_product,
):
    """Ensure the non shippable gift card are fulfilled when the flag for automatic
    fulfillment non shippable gift card is set."""
    # given
    channel = order_with_lines.channel
    channel.automatically_fulfill_non_shippable_gift_card = True
    channel.save()

    order = order_with_lines

    non_shippable_gift_card_line = order_with_lines.lines.first()
    non_shippable_variant = non_shippable_gift_card_product.variants.get()
    non_shippable_gift_card_line.variant = non_shippable_variant
    non_shippable_gift_card_line.is_gift_card = True
    non_shippable_gift_card_line.is_shipping_required = False
    non_shippable_gift_card_line.quantity = 1
    allocation = non_shippable_gift_card_line.allocations.first()
    allocation.quantity_allocated = 1
    allocation.save(update_fields=["quantity_allocated"])

    shippable_gift_card_line = order_with_lines.lines.last()
    shippable_variant = shippable_gift_card_product.variants.get()
    shippable_gift_card_line.variant = shippable_variant
    shippable_gift_card_line.is_gift_card = True
    shippable_gift_card_line.is_shipping_required = True
    shippable_gift_card_line.quantity = 1

    OrderLine.objects.bulk_update(
        [non_shippable_gift_card_line, shippable_gift_card_line],
        ["variant", "is_gift_card", "is_shipping_required", "quantity"],
    )

    manager = get_plugins_manager()

    order.payments.add(Payment.objects.create())
    order_info = fetch_order_info(order)

    # when
    handle_fully_paid_order(manager, order_info)

    # then
    flush_post_commit_hooks()
    assert order.events.filter(type=OrderEvents.ORDER_FULLY_PAID)

    mock_send_payment_confirmation.assert_called_once_with(order_info, manager)

    flush_post_commit_hooks()
    gift_card = GiftCard.objects.get()
    assert gift_card.ini