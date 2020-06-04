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
    variables = {"period": Reporti