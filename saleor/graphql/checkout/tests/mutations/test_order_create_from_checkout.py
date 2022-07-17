
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import ANY, patch

import graphene
import pytest
import pytz
from django.db.models.aggregates import Sum
from django.utils import timezone
from prices import Money

from .....checkout import calculations
from .....checkout.error_codes import OrderCreateFromCheckoutErrorCode
from .....checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from .....checkout.models import Checkout
from .....core.taxes import TaxError, zero_money, zero_taxed_money
from .....giftcard import GiftCardEvents
from .....giftcard.models import GiftCard, GiftCardEvent
from .....order import OrderOrigin, OrderStatus
from .....order.models import Fulfillment, Order
from .....plugins.manager import PluginsManager, get_plugins_manager
from .....tests.utils import flush_post_commit_hooks
from .....warehouse.models import Reservation, Stock, WarehouseClickAndCollectOption
from .....warehouse.tests.utils import get_available_quantity_for_stock
from ....tests.utils import assert_no_permission, get_graphql_content

MUTATION_ORDER_CREATE_FROM_CHECKOUT = """
mutation orderCreateFromCheckout(
        $id: ID!, $metadata: [MetadataInput!], $privateMetadata: [MetadataInput!]
    ){
    orderCreateFromCheckout(
            id: $id, metadata: $metadata, privateMetadata: $privateMetadata
        ){
        order{
            id
            token
            original
            origin
            total {
                currency
                net {
                    amount
                }
                gross {
                    amount
                }
            }
        }
        errors{
            field
            message
            code
            variants
        }
    }
}
"""


def test_order_from_checkout_with_inactive_channel(
    app_api_client,
    permission_handle_checkouts,
    checkout_with_gift_card,
    gift_card,
    address,
    shipping_method,
):
    assert not gift_card.last_used_on

    checkout = checkout_with_gift_card
    channel = checkout.channel
    channel.is_active = False
    channel.save()
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.metadata_storage.store_value_in_metadata(items={"accepted": "true"})
    checkout.metadata_storage.store_value_in_private_metadata(
        items={"accepted": "false"}
    )
    checkout.save()
    checkout.metadata_storage.save()

    variables = {"id": graphene.Node.to_global_id("Checkout", checkout.pk)}
    response = app_api_client.post_graphql(
        MUTATION_ORDER_CREATE_FROM_CHECKOUT,
        variables,
        permissions=[permission_handle_checkouts],
    )

    content = get_graphql_content(response)
    data = content["data"]["orderCreateFromCheckout"]
    assert (
        data["errors"][0]["code"]
        == OrderCreateFromCheckoutErrorCode.CHANNEL_INACTIVE.name
    )
    assert data["errors"][0]["field"] == "channel"


@pytest.mark.integration
@patch("saleor.order.calculations._recalculate_order_prices")
@patch("saleor.plugins.manager.PluginsManager.order_confirmed")
def test_order_from_checkout(
    order_confirmed_mock,
    _recalculate_order_prices_mock,
    app_api_client,
    permission_handle_checkouts,
    site_settings,
    checkout_with_gift_card,
    gift_card,
    address,
    shipping_method,
):
    assert not gift_card.last_used_on

    checkout = checkout_with_gift_card
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.metadata_storage.store_value_in_metadata(items={"accepted": "true"})
    checkout.metadata_storage.store_value_in_private_metadata(
        items={"accepted": "false"}
    )
    checkout.save()
    checkout.metadata_storage.save()

    checkout_line = checkout.lines.first()

    metadata_key = "md key"
    metadata_value = "md value"

    checkout_line.store_value_in_private_metadata({metadata_key: metadata_value})
    checkout_line.store_value_in_metadata({metadata_key: metadata_value})
    checkout_line.save()

    checkout_line_quantity = checkout_line.quantity
    checkout_line_variant = checkout_line.variant
    checkout_line_metadata = checkout_line.metadata
    checkout_line_private_metadata = checkout_line.private_metadata

    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    total = calculations.calculate_checkout_total_with_gift_cards(
        manager, checkout_info, lines, address
    )
    channel = checkout.channel
    channel.automatically_confirm_all_new_orders = True
    channel.save()

    orders_count = Order.objects.count()
    variables = {"id": graphene.Node.to_global_id("Checkout", checkout.pk)}
    response = app_api_client.post_graphql(
        MUTATION_ORDER_CREATE_FROM_CHECKOUT,
        variables,
        permissions=[permission_handle_checkouts],
    )

    content = get_graphql_content(response)
    data = content["data"]["orderCreateFromCheckout"]
    assert not data["errors"]

    order_token = data["order"]["token"]
    assert Order.objects.count() == orders_count + 1
    order = Order.objects.first()
    assert order.status == OrderStatus.UNFULFILLED
    assert order.origin == OrderOrigin.CHECKOUT
    assert not order.original
    assert str(order.pk) == order_token
    assert order.total.gross == total.gross
    assert order.metadata == checkout.metadata_storage.metadata
    assert order.private_metadata == checkout.metadata_storage.private_metadata

    order_line = order.lines.first()
    line_tax_class = order_line.variant.product.tax_class
    shipping_tax_class = shipping_method.tax_class

    assert checkout_line_quantity == order_line.quantity
    assert checkout_line_variant == order_line.variant
    assert checkout_line_metadata == order_line.metadata
    assert checkout_line_private_metadata == order_line.private_metadata

    assert order_line.tax_class == line_tax_class
    assert order_line.tax_class_name == line_tax_class.name
    assert order_line.tax_class_metadata == line_tax_class.metadata
    assert order_line.tax_class_private_metadata == line_tax_class.private_metadata

    assert order.shipping_address == address
    assert order.shipping_method == checkout.shipping_method
    assert order.shipping_tax_rate is not None
    assert order.shipping_tax_class_name == shipping_tax_class.name
    assert order.shipping_tax_class_metadata == shipping_tax_class.metadata
    assert (
        order.shipping_tax_class_private_metadata == shipping_tax_class.private_metadata
    )
    assert order.search_vector

    gift_card.refresh_from_db()
    assert gift_card.current_balance == zero_money(gift_card.currency)
    assert gift_card.last_used_on
    assert GiftCardEvent.objects.filter(
        gift_card=gift_card, type=GiftCardEvents.USED_IN_ORDER
    )

    order_confirmed_mock.assert_called_once_with(order)
    _recalculate_order_prices_mock.assert_not_called()


@pytest.mark.integration
@patch("saleor.plugins.manager.PluginsManager.order_confirmed")
def test_order_from_checkout_with_metadata(
    order_confirmed_mock,
    app_api_client,
    permission_handle_checkouts,
    permission_manage_checkouts,
    site_settings,
    checkout_with_gift_card,
    gift_card,
    address,
    shipping_method,
):
    # given
    checkout = checkout_with_gift_card
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.metadata_storage.store_value_in_metadata(items={"accepted": "true"})
    checkout.metadata_storage.store_value_in_private_metadata(
        items={"accepted": "false"}
    )
    checkout.save()
    checkout.metadata_storage.save()

    metadata_key = "md key"
    metadata_value = "md value"

    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    total = calculations.calculate_checkout_total_with_gift_cards(
        manager, checkout_info, lines, address
    )
    channel = checkout.channel
    channel.automatically_confirm_all_new_orders = True
    channel.save()

    orders_count = Order.objects.count()
    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout.pk),
        "metadata": [{"key": metadata_key, "value": metadata_value}],
        "privateMetadata": [{"key": metadata_key, "value": metadata_value}],
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_ORDER_CREATE_FROM_CHECKOUT,
        variables,
        permissions=[permission_handle_checkouts, permission_manage_checkouts],
    )

    content = get_graphql_content(response)
    data = content["data"]["orderCreateFromCheckout"]
    assert not data["errors"]

    order_token = data["order"]["token"]
    assert Order.objects.count() == orders_count + 1
    order = Order.objects.first()
    assert order.status == OrderStatus.UNFULFILLED
    assert order.origin == OrderOrigin.CHECKOUT
    assert not order.original
    assert str(order.pk) == order_token
    assert order.total.gross == total.gross
    assert order.metadata == {
        **checkout.metadata_storage.metadata,
        **{metadata_key: metadata_value},
    }
    assert order.private_metadata == {
        **checkout.metadata_storage.private_metadata,
        **{metadata_key: metadata_value},
    }
    order_confirmed_mock.assert_called_once_with(order)


def test_order_from_checkout_by_app_with_missing_permission(
    app_api_client,
    checkout_with_item,
    customer_user,
    address,
    shipping_method,
):
    checkout = checkout_with_item
    checkout.user = customer_user
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.save()

    variables = {"id": graphene.Node.to_global_id("Checkout", checkout.pk)}

    response = app_api_client.post_graphql(
        MUTATION_ORDER_CREATE_FROM_CHECKOUT,
        variables,
    )

    assert_no_permission(response)


@patch("saleor.giftcard.utils.send_gift_card_notification")
@patch("saleor.plugins.manager.PluginsManager.order_confirmed")
def test_order_from_checkout_gift_card_bought(
    order_confirmed_mock,
    send_notification_mock,
    site_settings,
    customer_user,
    app_api_client,
    app,
    permission_handle_checkouts,
    checkout_with_gift_card_items,
    address,
    shipping_method,
    payment_txn_captured,
):
    # given
    checkout = checkout_with_gift_card_items
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.metadata_storage.store_value_in_metadata(items={"accepted": "true"})
    checkout.metadata_storage.store_value_in_private_metadata(
        items={"accepted": "false"}
    )
    checkout.user = customer_user
    checkout.save()
    checkout.metadata_storage.save()

    manager = get_plugins_manager()
    lines, _ = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)

    amount = calculations.calculate_checkout_total_with_gift_cards(
        manager, checkout_info, lines, address
    ).gross.amount

    payment_txn_captured.order = None
    payment_txn_captured.checkout = checkout