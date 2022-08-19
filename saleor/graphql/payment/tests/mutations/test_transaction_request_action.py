from decimal import Decimal

import graphene
import pytest
from mock import patch

from .....order import OrderEvents
from .....payment import TransactionAction
from .....payment.interface import TransactionActionData
from .....payment.models import TransactionItem
from ....core.enums import TransactionRequestActionErrorCode
from ....tests.utils import assert_no_permission, get_graphql_content
from ...enums import TransactionActionEnum

MUTATION_TRANSACTION_REQUEST_ACTION = """
mutation TransactionRequestAction(
    $id: ID!,
    $action_type: TransactionActionEnum!,
    $amount: PositiveDecimal
    ){
    transactionRequestAction(
            id: $id,
            actionType: $action_type,
            amount: $amount
        ){
        transaction{
                id
                actions
                reference
                type
                status
                modifiedAt
                createdAt
                authorizedAmount{
                    amount
                    currency
                }
                voidedAmount{
                    currency
                    amount
                }
                chargedAmount{
                    currency
                    amount
                }
                refundedAmount{
                    currency
                    amount
                }
        }
        errors{
            field
            message
            code
        }
    }
}
"""


@pytest.mark.parametrize(
    "charge_amount, expected_called_charge_amount",
    [
        (Decimal("8.00"), Decimal("8.00")),
        (None, Decimal("10.00")),
        (Decimal("100"), Decimal("10.00")),
    ],
)
@patch("saleor.plugins.manager.PluginsManager.is_event_active_for_any_plugin")
@patch("saleor.plugins.manager.PluginsManager.transaction_action_request")
def test_transaction_request_charge_action_for_order(
    mocked_payment_action_request,
    mocked_is_active,
    charge_amount,
    expected_called_charge_amount,
    order_with_lines,
    app_api_client,
    permission_manage_payments,
):
    # given
    mocked_is_active.return_value = True

    transaction = TransactionItem.objects.create(
        status="Authorized",
        type="Credit card",
        reference="PSP ref",
        available_actions=["charge", "void"],
        currency="USD",
        order_id=order_with_lines.pk,
        authorized_value=Decimal("10"),
    )

    variables = {
        "id": graphene.Node.to_global_id("TransactionItem", transaction.pk),
        "action_type": TransactionActionEnum.CHARGE.name,
        "amount": charge_amount,
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_REQUEST_ACTION,
        variables,
        permissions=[permission_manage_payments],
    )

    # then
    get_graphql_content(response)

    assert mocked_is_active.called
    mocked_payment_action_request.assert_called_once_with(
        TransactionActionData(
            transaction=transaction,
            action_type=TransactionAction.CHARGE,
            action_value=expected_called_charge_amount,
        ),
        channel_slug=order_with_lines.channel.slug,
    )

    event = order_with_lines.events.first()
    assert event.type == OrderEvents.TRANSACTION_CAPTURE_REQUESTED
    assert Decimal(event.parameters["amount"]) == expected_called_charge_amount
    assert event.parameters["reference"] == transaction.reference


@pytest.mark.parametrize(
    "refund_amount, expected_called_refund_amount",
    [
        (Decimal("8.00"), Decimal("8.00")),
        (None, Decimal("10.00")),
        (Decimal("100"), Decimal("10.00")),
    ],
)
@patch("saleor.plugins.manager.PluginsManager.is_event_active_for_any_plugin")
@patch("saleor.plugins.manager.PluginsManager.transaction_action_request")
def test_transaction_request_refund_action_for_order(
    mocked_payment_action_request,
    mocked_is_active,
    refund_amount,
    expected_called_refund_amount,
    order_with_lines,
    app_api_client,
    permission_manage_payments,
):
    # given
    mocked_is_active.return_value = True

    transaction = TransactionItem.objects.create(
        status="Captured",
        type="Credit card",
        reference="PSP ref",
        available_actions=["refund"],
        currency="USD",
        order_id=order_with_lines.pk,
        charged_value=Decimal("10"),
    )

    variables = {
        "id": graphene.Node.to_global_id("TransactionItem", transaction.pk),
        "action_type": TransactionActionEnum.REFUND.name,
        "amount": refund_amount,
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_REQUEST_ACTION,
        variables,
        permissions=[permission_manage_payments],
    )

    # then
    get_graphql_content(response)

    assert mocked_is_active.called
    mocked_payment_action_request.assert_called_once_with(
        TransactionActionData(
            transaction=transaction,
            action_type=TransactionAction.REFUND,
            action_value=expected_called_refund_amount,
        ),
        channel_slug=order_with_lines.channel.slug,
    )

    ev