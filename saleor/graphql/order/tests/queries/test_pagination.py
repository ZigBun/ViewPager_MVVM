from datetime import date, timedelta
from decimal import Decimal

import graphene
import pytest
from freezegun import freeze_time
from prices import Money, TaxedMoney

from .....core.postgres import FlatConcatSearchVector
from .....discount.models import OrderDiscount
from .....order.models import Order, OrderStatus
from .....order.search import (
    prepare_order_search_vector_value,
    update_order_search_vector,
)
from .....payment import ChargeStatus
from ....tests.utils import get_graphql_content


@pytest.fixture()
def orders_for_pagination(db, channel_USD):
    orders = Order.objects.bulk_create(
        [
            Order(
                total=TaxedMoney(net=Money(1, "USD"), gross=Money(1, "USD")),
                channel=channel_USD,
            ),
            Order(
                total=TaxedMoney(net=Money(2, "USD"), gross=Money(2, "USD")),
                channel=channel_USD,
            ),
            Order(
                total=TaxedMoney(net=Money(3, "USD"), gross=Money(3, "USD")),
                channel=channel_USD,
            ),
        ]
    )

    for order in orders:
        order.search_vector = FlatConcatSearchVector(
            *prepare_order_search_vector_value(order)
        )
    Order.objects.bulk_update(orders, ["search_vector"])

    return orders


@pytest.fixture()
def draft_orders_for_pagination(db, channel_USD):
    orders = Order.objects.bulk_create(
        [
            Order(
                total=TaxedMoney(net=Money(1, "USD"), gross=Money(1, "USD")),
                status=OrderStatus.DRAFT,
                channel=channel_USD,
                should_refresh_prices=False,
            ),
            Order(
                total=TaxedMoney(net=Money(2, "USD"), gross=Money(2, "USD")),
                status=OrderStatus.DRAFT,
                channel=channel_USD,
                should_refresh_prices=False,
            ),
            Order(
                total=TaxedMoney(net=Money(3, "USD"), gross=Money(3, "USD")),
                status=OrderStatus.DRAFT,
                channel=channel_USD,
                should_refresh_prices=False,
            ),
        ]
    )
    return orders


QUERY_ORDERS_WITH_PAGINATION = """
    query (
        $first: Int, $last: Int, $after: String, $before: String,
        $sortBy: OrderSortingInput, $filter: OrderFilterInput
    ){
        orders(
            first: $first, last: $last, after: $after, before: $before,
            sortBy: $sortBy, filter: $filter
        ) {
            totalCount
            edges {
                node {
                    id
                    number
                    total{
                        gross{
                            amount
                        }
                    }
                }
            }
            pageInfo{
                startCursor
                endCursor
                hasNextPage
                hasPreviousPage
            }
        }
    }
"""

QUERY_DRAFT_ORDERS_WITH_PAGINATION = """
    query (
        $first: Int, $last: Int, $after: String, $before: String,
        $sortBy: OrderSortingInput, $filter: OrderDraftFilterInput
    ){
        draftOrders(
            first: $first, last: $last, after: $after, before: $before,
            sortBy: $sortBy, filter: $filter
        ) {
            totalCount
            edges {
                node {
                    id
                    number
                    total{
                        gross{
                            amount
                        }
                    }
                    created
                }
            }
            pageInfo{
                startCursor
                endCursor
                hasNextPage
                hasPreviousPage
            }
        }
    }
"""


@pytest.mark.parametrize(
    "orders_filter, orders_order, expected_total_count",
    [
        (
            {
                "created": {
                    "gte": str(date.today() - timedelta(days=3)),
                    "lte": str(date.today()),
                }
            },
            [3.0, 2.0],
            3,
        ),
        ({"created": {"gte": str(date.today() - timedelta(days=3))}}, [3.0, 2.0], 3),
        ({"created": {"lte": str(date.today())}}, [0.0, 3.0], 4),
        ({"created": {"lte": str(date.today() - timedelta(days=3))}}, [0.0], 1),
        ({"created": {"gte": str(date.today() + timedelta(days=1))}}, [], 0),
    ],
)
def test_order_query_pagination_with_filter_created(
    orders_filter,
    orders_order,
    expected_total_count,
    staff_api_client,
    permission_manage_orders,
    orders_for_pagination,
    channel_USD,
):
    with freeze_time("2012-01-14"):
        Order.objects.create(channel=channel_USD)
    page_size = 2
    variables = {"first": page_size, "after": None, "filter": orders_filter}
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    response = staff_api_client.post_graphql(QUERY_ORDERS_WITH_PAGINATION, variables)
    content = get_graphql_content(response)

    orders = content["data"]["orders"]["edges"]
    total_count = content["data"]["orders"]["totalCount"]

    for i in range(total_count if total_count < page_size else page_size):
    