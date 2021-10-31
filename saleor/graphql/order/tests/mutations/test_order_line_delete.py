from unittest.mock import patch

import graphene
import pytest
from django.db.models import Sum

from .....order import OrderStatus
from .....order import events as order_events
from .....order.models import OrderEvent
from .....warehouse.models import Stock
from ....tests.utils import get_graphql_content
from ..utils import assert_proper_webhook_called_once

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
                    net {
                        currency
                        amount
                    }
                }
            }
        }
    }
"""


@patch("saleor.plugins.manager.PluginsManager.product_variant_back_in_stock")
def test_order_line_remove_with_back_in_stock_webhook(
    back_in_stock_webhook_mock,
    order_with_lines,
    permission_manage_orders,
    staff_api_client,
):
    Stock.objects.update(quantity=3)
    first_stock = Stock.objects.first()
    assert (
        first_stock.quantity
        - (
            first_stock.allocations.aggregate(Sum("quantity_allocated"))[
                "quantity_allocated__sum"
            ]
            or 0
        )
    ) == 0

    query = ORDER_LINE_DELETE_MUTATION
    order = order_with_lines
    order.status = OrderStatus.UNCONFIRMED
    order.save(update_fields=["status"])

    line = order.lines.first()

    line_id = graphene.Node.to_global_id("OrderLine", line.id)
    variables = {"id": line_id}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderLineDelete"]
    assert OrderEvent.objects.count() == 1
    assert OrderEvent.objects.last().type == order_events.OrderEvents.REMOVED_PRODUCTS
    assert data["orderLine"]["id"] == line_id
    assert line not in order.lines.all()
    first_stock.refresh_from_db()
    assert (
        first_stock.quantity
        - (
            first_stock.allocations.aggregate(Sum("quantity_allocated"))[
                "quantity_allocated__sum"
            ]
            or 0
        )
    ) == 3
    back_in_stock_webhook_mock.assert_called_once_with(Stock.objects.first())


@pytest.mark.parametrize("status", (OrderStatus.DRAFT, OrderStatus.UNCONFIRMED))
@patch("saleor.plugins.manager.PluginsManager.draft_order_updated")
@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_line_remove(
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
    line_id = graphene.Node.to_global_id("OrderLine", line.id)
    variables = {"id": line_id}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderLineDelete"]
    assert OrderEvent.objects.count() == 1
    assert OrderEvent.objects.last().type == order_events.Or