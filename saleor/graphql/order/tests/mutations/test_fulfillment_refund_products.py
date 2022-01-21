from decimal import Decimal
from unittest.mock import ANY, patch

import graphene
from prices import Money, TaxedMoney

from .....core.prices import quantize_price
from .....order import FulfillmentLineData, OrderEvents
from .....order.error_codes import OrderErrorCode
from .....order.fetch import OrderLineInfo
from .....order.models import FulfillmentLine, FulfillmentStatus
from .....payment import ChargeStatus, PaymentError, TransactionAction
from .....payment.interface import RefundData, TransactionActionData
from .....payment.models import TransactionItem
from .....warehouse.models import Allocation, Stock
from ....core.utils import to_global_id_or_none
from ....tests.utils import get_graphql_content

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
                orderLine{
                    id
                }
            }
        }
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


@patch("saleor.plugins.manager.PluginsManager.is_event_active_for_any_plugin")
@patch("saleor.plugins.manager.PluginsManager.transaction_action_request")
def test_fulfillment_refund_products_with_transaction_action_request(
    mocked_transaction_action_request,
    mocked_is_active,
    staff_api_client,
    permission_manage_orders,
    fulfilled_order,
):
    # given
    mocked_is_active.return_value = True

    charged_value = Decimal("20.0")
    transaction = TransactionItem.objects.create(
        status="Captured",
        type="Credit card",
        reference="PSP ref",
        available_actions=["refund"],
        currency="USD",
        order_id=fulfilled_order.pk,
        charged_value=charged_value,
    )

    order_id = to_global_id_or_none(fulfilled_order)
    amount_to_refund = Decimal("11.00")
    variables = {
        "order": order_id,
        "input": {"amountToRefund": amount_to_refund, "includeShippingCosts": True},
    }
    staff_api_client.user.user_permissions.add(permission_manage_orders)

    # when
    response = staff_api_client.post_graphql(ORDER_FULFILL_REFUND_MUTATION, variables)

    # then
    content = get_graphql_content(response)
    data = content["data"]["orderFulfillmentRefundProducts"]
    errors = data["errors"]
    assert not errors

    mocked_transaction_action_request.assert_called_once_with(
        TransactionActionData(
            transaction=transaction,
            action_type=TransactionAction.REFUND,
            action_value=amount_to_refund,
        ),
        channel_slug=fulfilled_order.channel.slug,
    )
    event = fulfilled_order.events.first()
    assert event.type == OrderEvents.TRANSACTION_REFUND_REQUESTED
    assert Decimal(event.parameters["amount"]) == amount_to_refund
    assert event.parameters["reference"] == transaction.reference


@patch("saleor.plugins.manager.PluginsManager.is_event_active_for_any_plugin")
def test_fulfillment_refund_products_with_missing_payment_action_hook(
    mocked_is_active,
    staff_api_client,
    permission_manage_orders,
    fulfilled_order,
):
    # given
    mocked_is_active.return_value = False

    charged_value = Decimal("20.0")
    TransactionItem.objects.create(
        status="Captured",
        type="Credit card",
        reference="PSP ref",
        available_actions=["refund"],
        currency="USD",
        order_id=fulfilled_order.pk,
        charged_value=charged_value,
    )

    order_id = to_global_id_or_none(fulfi