from unittest.mock import ANY, patch

import graphene

from .....core.notify_events import NotifyEventType
from .....core.tests.utils import get_site_context_payload
from .....order import OrderStatus
from .....order import events as order_events
from .....order.error_codes import OrderErrorCode
from .....order.fetch import fetch_order_info
from .....order.models import OrderEvent
from .....order.notifications import get_default_order_payload
from .....product.models import ProductVariant
from ....core.utils import to_global_id_or_none
from ....tests.utils import get_graphql_content

ORDER_CONFIRM_MUTATION = """
    mutation orderConfirm($id: ID!) {
        orderConfirm(id: $id) {
            errors {
                field
                code
            }
            order {
                status
            }
        }
    }
"""


@patch("saleor.order.actions.handle_fully_paid_order")
@patch("saleor.plugins.manager.PluginsManager.notify")
@patch("saleor.payment.gateway.capture")
def test_order_confirm(
    capture_mock,
    mocked_notify,
    handle_fully_paid_order_mock,
    staff_api_client,
    order_unconfirmed,
    permission_manage_orders,
    payment_txn_preauth,
    site_settings,
):
    # given
    payment_txn_preauth.order = order_unconfirmed
    payment_txn_preauth.captured_amount = order_unconfirmed.total.gross.amount
    payment_txn_preauth.total = order_unconfirmed.total.gross.amount
    payment_txn_preauth.save(update_fields=["order", "captured_amount", "total"])

    order_unconfirmed.total_charged = order_unconfirmed.total.gross
    order_unconfirmed.save(update_fields=["total_charged_amount"])

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    assert not OrderEvent.objects.exists()

    # when
    response = staff_api_client.post_graphql(
        ORDER_CONFIRM_MUTATION,
        {"id": graphene.Node.to_global_id("Order", order_unconfirmed.id)},
    )

    # then
    order_data = get_graphql_content(response)["data"]["orderConfirm"]["order"]

    assert order_data["status"] == OrderStatus.UNFULFILLED.upper()
    order_unconfirmed.refresh_from_db()
    assert order_unconfirmed.status == OrderStatus.UNFULFILLED
    assert OrderEvent.objects.count() == 2
    assert OrderEvent.objects.filter(
        order=order_unconfirmed,
        user=staff_api_client.user,
        type=order_events.OrderEvents.CONFIRMED,
    ).exists()

    assert OrderEvent.objects.filter(
        order=order_unconfirmed,
        user=staff_api_client.user,
        type=order_events.OrderEvents.PAYMENT_CAPTURED,
        parameters__amount=payment_txn_preauth.get_total().amount,
    ).exists()

    capture_mock.assert_called_once_with(
        payment_txn_preauth, ANY, channel_slug=order_unconfirmed.channel.slug
    )
    expected_payload = {
        "order": get_default_order_payload(order_unconfirmed, ""),
        "recipient_email": order_unconfirmed.user.email,
        "requester_user_id": to_global_id_or_none(staff_api_client.user),
        "requester_app_id": None,
        **get_site_context_payload(site_settings.site),
    }
    mocked_notify.assert_called_once_with(
        NotifyEventType.ORDER_CONFIRMED,
        expected_payload,
        channel_slug=order_unconfirmed.channel.slug,
    )
    order_info = fetch_order_info(order_unconfirmed)
    handle_fully_paid_order_mock.assert_called_once_with(
        ANY, order_info, staff_api_client.user, None, site_settings
    )


@patch("saleor.plugins.manager.PluginsManager.notify")
@patch("saleor.payment.gateway.capture")
def test_order_confirm_without_sku(
    capture_mock,
    mocked_notify,
    staff_api_client,
    order_unconfirmed,
    permission_manage_orders,
    payment_txn_preauth,
    site_settings,
):
    order_unconfirmed.lines.update(product_sku=None)
    ProductVariant.objects.update(sku=None)

    payment_txn_preauth.order = order_unconfirm