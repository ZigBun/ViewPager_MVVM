from decimal import Decimal

import pytest
from prices import Money, TaxedMoney

from ...checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from ...discount import DiscountValueType, OrderDiscountType
from ...giftcard import GiftCardEvents
from ...giftcard.models import GiftCardEvent
from ...graphql.order.utils import OrderLineData
from ...plugins.manager import get_plugins_manager
from .. import OrderStatus
from ..events import OrderEvents
from ..fetch import OrderLineInfo
from ..models import Order, OrderEvent
from ..utils import (
    add_gift_cards_to_order,
    add_variant_to_order,
    change_order_line_quantity,
    get_order_country,
    get_total_order_discount_excluding_shipping,
    get_valid_shipping_methods_for_order,
    match_orders_with_new_user,
    update_order_display_gross_prices,
)


@pytest.mark.parametrize(
    "status, previous_quantity, new_quantity, added_count, removed_count",
    (
        (OrderStatus.DRAFT, 5, 2, 0, 3),
        (OrderStatus.UNCONFIRMED, 2, 5, 3, 0),
        (OrderStatus.UNCONFIRMED, 2, 0, 0, 2),
        (OrderStatus.DRAFT, 5, 5, 0, 0),
    ),
)
def test_change_quantity_generates_proper_event(
    status,
    previous_quantity,
    new_quantity,
    added_count,
    removed_count,
    order_with_lines,
    staff_user,
):
    assert not OrderEvent.objects.exists()
    order_with_lines.status = status
    order_with_lines.save(update_fields=["status"])

    line = order_with_lines.lines.last()
    line.quantity = previous_quantity

    line_info = OrderLineInfo(
        line=line,
        quantity=line.quantity,
        variant=line.variant,
        warehouse_pk=line.allocations.first().stock.warehouse.pk,
    )
    stock = line.allocations.first().stock
    stock.quantity = 5
    stock.save(update_fields=["quantity"])
    app = None

    change_order_line_quantity(
        staff_user,
        app,
        line_info,
        previous_quantity,
        new_quantity,
        order_with_lines.channel,
        get_plugins_manager(),
    )

    if removed_count:
        expected_type = OrderEvents.REMOVED_PRODUCTS
        expected_quantity = removed_count
    elif added_count:
        expected_type = OrderEvents.ADDED_PRODUCTS
        expected_quantity = added_count
    else:
        # No event should have occurred
        assert not OrderEvent.objects.exists()
        return

    new_event = OrderEvent.objects.last()  # type: OrderEvent
    assert new_event.type == expected_type
    assert new_event.user == staff_user
    expected_line_pk = None if new_quantity == 0 else str(line.pk)
    assert new_event.parameters == {
        "lines": [
            {
                "quantity": expected_quantity,
                "line_pk": expected_line_pk,
                "item": str(line),
            }
        ]
    }


def test_change_quantity_update_line_fields(
    order_with_lines,
    staff_user,
):
    # given
    line = order_with_lines.lines.last()
    line_info = OrderLineInfo(
        line=line,
        quantity=line.quantity,
        variant=line.variant,
        warehouse_pk=line.allocations.first().stock.warehouse.pk,
    )
    new_quantity = 5
    app = None

    # when
    change_order_line_quantity(
        staff_user,
        app,
        line_info,
        line.quantity,
        new_quantity,
        order_with_lines.channel,
        get_plugins_manager(),
    )

    # then
    line.refresh_from_db()
    assert line.quantity == new_quantity
    assert line.total_price == line.unit_price * new_quantity
    assert line.undiscounted_total_price == line.undiscounted_unit_price * new_quantity


def test_match_orders_with_new_user(order_list, staff_user, customer_user):
    # given
    for order in order_list[:2]:
        order.user = None
        order.user_email = staff_user.email

    order_with_user = order_list[-1]
    order_with_user.user = customer_user
    order_with_user.user_email = staff_user.email

    Order.objects.bulk_update(order_list, ["user", "user_email"])

    # when
    match_orders_with_new_user(staff_user)

    # then
    for order in order_list[:2]:
        order.refresh_from_db()
        assert order.user == staff_user

    order_with_user.refresh_from_db()
    assert order_with_user.user != staff_user


def test_match_draft_order_with_new_user(customer_user, channel_USD):
    address = customer_user.default_billing_address.get_copy()
    order = Order.objects.create(
        billing_address=address,
        user=None,
        user_email=customer_user.email,
        status=OrderStatus.DRAFT,
        channel=channel_USD,
    )
    match_orders_with_new_user(customer_user)

    order.refresh_from_db()
    assert order.user is None


def test_get_valid_shipping_methods_for_order(order_line_with_one_allocation, address):
    # given
    order = order_line_with_one_allocation.order
    order_line_with_one_allocation.is_shipping_required = True
    order_line_with_one_allocation.save(update_fields=["is_shipping_required"])

    order.currency = "USD"
    order.shipping_address = address
    order.save(update_fields=["shipping_address"])

    # when
    valid_shipping_methods = get_valid_shipping_methods_for_order(
        order, order.channel.shipping_method_listings.all(), get_plugins_manager()
    )

    # then
    assert len(valid_shipping_methods) == 1


def test_get_valid_shipping_methods_for_order_no_channel_shipping_zones(
    order_line_with_one_allocation, address
):
    # given
    order = order_line_with_one_allocation.order
    order.channel.shipping_zones.clear()
    order_line_with_one_allocation.is_shipping_required = True
    order_line_with_one_allocation.save(update_fields=["is_shipping_required"])

    order.currency = "USD"
    order.shipping_address = address
    order.save(update_fields=["shipping_address"])

    # when
    valid_shipping_methods = get_valid_shipping_methods_for_order(
        order, order.channel.shipping_method_listings.all(), get_plugins_manager()
    )

    # then
    assert len(valid_shipping_methods) == 0


def test_get_valid_shipping_methods_for_order_no_shipping_address(
    order_line_with_one_allocation, address
):
    # given
    order = order_line_with_one_allocation.order
    order_line_with_one_allocation.is_shipping_required = True
    order_line_with_one_allocation.save(update_fields=["is_shipping_required"])

    order.currency = "USD"

    # when
    valid_shipping_methods = get_valid_shipping_methods_for_order(
        order, order.channel.shipping_method_listings.all(), get_plugins_manager()
    )

    # then
    assert valid_shipping_methods == []


def test_get_valid_shipping_methods_for_order_shipping_not_required(
    order_line_with_one_allocation, address
):
    # given
    order = order_line_with_one_allocation.order
    order_line_with_one_allocation.is_shipping_required = False
    order_line_with_one_allocation.save(update_fields=["is_shipping_required"])

    order.currency = "USD"
    order.shipping_address = address
    order.save(update_fields=["shipping_address"])

    # when
    valid_shipping_methods = get_valid_shipping_methods_for_order(
        order, order.channel.shipping_method_listings.all(), get_plugins_manager()
    )

    # then
    assert valid_shipping_methods == []


def test_add_variant_to_order(
    order, customer_user, variant, site_settings, discount_info
):
    # given
    