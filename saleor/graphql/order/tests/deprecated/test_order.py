import warnings
from decimal import Decimal
from functools import partial
from unittest.mock import ANY, patch

import graphene
import pytest
from prices import Money, TaxedMoney, fixed_discount

from .....channel.utils import DEPRECATION_WARNING_MESSAGE
from .....core.prices import quantize_price
from .....discount import DiscountValueType
from .....order import OrderEvents, OrderOrigin, OrderStatus
from .....order import events as order_events
from .....order.fetch import OrderLineInfo
from .....order.interface import OrderTaxedPricesData
from .....order.models import FulfillmentStatus, Order, OrderEvent, OrderLine
from .....payment import ChargeStatus
from .....payment.interface import RefundData
from ....core.enums import ReportingPeriod
from ....discount.enums import DiscountValueTypeEnum
from ....tests.utils import get_graphql_content


def assert_proper_webhook_called_once(order, status, draft_mock, order_mock):
    if status == OrderStatus.DRAFT:
        draft_mock.assert_called_once_with(order)
        order_mock.assert_not_called()
    else:
        draft_mock.assert_not_called()
        order_mock.assert_called_once_with(order)


QUERY_ORDER_TOTAL = """
query Orders($period: ReportingPeriod, $channel: String) {
    ordersTotal(period: $period, channel: $channel ) {
        gross {
            amount
            currency
        }
        net {
            currency
            amount
        }
    }
}
"""


def test_orders_total(staff_api_client, permission_manage_orders, order_with_lines):
    # given
    order = order_with_lines
    variables = {"period": ReportingPeriod.TODAY.name}

    # when
    with warnings.catch_warnings(record=True) as warns:
        response = staff_api_client.post_graphql(
            QUERY_ORDER_TOTAL, variables, permissions=[permission_manage_orders]
        )
        content = get_graphql_content(response)

    # then
    amount = str(content["data"]["ordersTotal"]["gross"]["amount"])
    assert Money(amount, "USD") == order.total.gross
    assert any(
        [str(warning.message) == DEPRECATION_WARNING_MESSAGE for warning in warns]
    )


ORDER_LINE_DELETE_MUTATION = """
    mutation OrderLineDelete($id: ID!) {
        orderLineDelete(id: $id) {
            errors {
                field
                message
            }
            orderLine {
                id
            }
            order {
                id
                total{
                    gross{
                        currency
                        amount
                    }
                }
            }
        }
    }
"""


@pytest.mark.parametrize("status", (OrderStatus.DRAFT, OrderStatus.UNCONFIRMED))
@patch("saleor.plugins.manager.PluginsManager.draft_order_updated")
@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_line_remove_by_old_line_id(
    order_updated_webhook_mock,
    draft_order_updated_webhook_mock,
    status,
    order_with_lines,
    permission_manage_orders,
    staff_api_client,
):
    query = ORDER_LINE_DELETE_MUTATION
    order = order_with_lines
    order.status = status
    order.save(update_fields=["status"])
    line = order.lines.first()
    line.old_id = 1
    line.save(update_fields=["old_id"])

    line_id = graphene.Node.to_global_id("OrderLine", line.old_id)
    variables = {"id": line_id}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderLineDelete"]
    assert OrderEvent.objects.count() == 1
    assert OrderEvent.objects.last().type == order_events.OrderEvents.REMOVED_PRODUCTS
    assert data["orderLine"]["id"] == graphene.Node.to_global_id("OrderLine", line.pk)
    assert line not in order.lines.all()
    assert_proper_webhook_called_once(
        order, status, draft_order_updated_webhook_mock, order_updated_webhook_mock
    )


ORDER_LINE_UPDATE_MUTATION = """
    mutation OrderLineUpdate($lineId: ID!, $quantity: Int!) {
        orderLineUpdate(id: $lineId, input: {quantity: $quantity}) {
            errors {
                field
                message
            }
            orderLine {
                id
                quantity
            }
            order {
                total {
                    gross {
                        amount
                    }
                }
            }
        }
    }
"""


@pytest.mark.parametrize("status", (OrderStatus.DRAFT, OrderStatus.UNCONFIRMED))
@patch("saleor.plugins.manager.PluginsManager.draft_order_updated")
@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_line_update_by_old_line_id(
    order_updated_webhook_mock,
    draft_order_updated_webhook_mock,
    status,
    order_with_lines,
    permission_manage_orders,
    staff_api_client,
    staff_user,
):
    # given
    query = ORDER_LINE_UPDATE_MUTATION
    order = order_with_lines
    order.status = status
    order.save(update_fields=["status"])
    line = order.lines.first()
    line.old_id = 1
    line.save(update_fields=["old_id"])

    new_quantity = 1
    removed_quantity = 2
    line_id = graphene.Node.to_global_id("OrderLine", line.old_id)
    variables = {"lineId": line_id, "quantity": new_quantity}
    staff_api_client.user.user_permissions.add(permission_manage_orders)

    # Ensure the line has the expected quantity
    assert line.quantity == 3

    # No event should exist yet
    assert not OrderEvent.objects.exists()

    # when
    response = staff_api_client.post_graphql(query, variables)

    # then
    content = get_graphql_content(response)
    data = content["data"]["orderLineUpdate"]
    assert data["orderLine"]["quantity"] == new_quantity
    assert_proper_webhook_called_once(
        order, status, draft_order_updated_webhook_mock, order_updated_webhook_mock
    )
    removed_items_event = OrderEvent.objects.last()  # type: OrderEvent
    assert removed_items_event.type == order_events.OrderEvents.REMOVED_PRODUCTS
    assert removed_items_event.user == staff_user
    assert removed_items_event.parameters == {
        "lines": [
            {"quantity": removed_quantity, "line_pk": str(line.pk), "item": str(line)}
        ]
    }


ORDER_FULFILL_QUERY = """
    mutation fulfillOrder(
        $order: ID, $input: OrderFulfillInput!
    ) {
        orderFulfill(
            order: $order,
            input: $input
        ) {
            errors {
                field
                code
                message
                warehouse
                orderLines
            }
        }
    }
"""


@pytest.mark.parametrize("fulfillment_auto_approve", [True, False])
@patch("saleor.graphql.order.mutations.order_fulfill.create_fulfillments")
def test_order_fulfill_old_line_id(
    mock_create_fulfillments,
    fulfillment_auto_approve,
    staff_api_client,
    staff_user,
    order_with_lines,
    permission_manage_orders,
    warehouse,
    site_settings,
):
    site_settings.fulfillment_auto_approve = fulfillment_auto_approve
    site_settings.save(update_fields=["fulfillment_auto_approve"])
    order = order_with_lines
    query = ORDER_FULFILL_QUERY
    order_id = graphene.Node.to_global_id("Order", order.id)
    order_line, order_line2 = order.lines.all()
    order_line.old_id = 1
    order_line2.old_id = 2
    OrderLine.objects.bulk_update([order_line, order_line2], ["old_id"])

    order_line_id = graphene.Node.to_global_id("OrderLine", order_line.old_id)
    order_line2_id = graphene.Node.to_global_id("OrderLine", order_line2.id)
    warehouse_id = graphene.Node.to_global_id("Warehouse", warehouse.pk)
    variables = {
        "order": order_id,
        "input": {
            "notifyCustomer": True,
            "lines": [
                {
                    "orderLineId": order_line_id,
                    "stocks": [{"quantity": 3, "warehouse": warehouse_id}],
                },
                {
                    "orderLineId": order_line2_id,
                    "stocks": [{"quantity": 2, "warehouse": warehouse_id}],
                },
            ],
        },
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderFulfill"]
    assert not data["errors"]

    fulfillment_lines_for_warehouses = {
        warehouse.pk: [
            {"order_line": order_line, "quantity": 3},
            {"order_line": order_line2, "quantity": 2},
        ]
    }
    mock_create_fulfillments.assert_called_once_with(
        staff_user,
        None,
        order,
        fulfillment_lines_for_warehouses,
        ANY,
        site_settings,
        True,
        allow_stock_to_be_exceeded=False,
        approved=fulfillment_auto_approve,
        tracking_number="",
    )


ORDER_FULFILL_REFUND_MUTATION = """
mutation OrderFulfillmentRefundProducts(
    $order: ID!, $input: OrderRefundProductsInput!
) {
    orderFulfillmentRefundProducts(
        order: $order,
        input: $input
    ) {
        fulfillment{
            id
            status
            lines{
                id
                quantity
      