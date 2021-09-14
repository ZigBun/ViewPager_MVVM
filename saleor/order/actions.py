import logging
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple, TypedDict
from uuid import UUID

from django.contrib.sites.models import Site
from django.db import transaction

from ..account.models import User
from ..core import analytics
from ..core.exceptions import AllocationError, InsufficientStock, InsufficientStockData
from ..core.tracing import traced_atomic_transaction
from ..core.transactions import transaction_with_commit_on_errors
from ..core.utils.events import call_event
from ..giftcard import GiftCardLineData
from ..payment import (
    ChargeStatus,
    CustomPaymentChoices,
    PaymentError,
    TransactionKind,
    gateway,
)
from ..payment.gateway import request_refund_action
from ..payment.interface import RefundData
from ..payment.models import Payment, Transaction, TransactionItem
from ..payment.utils import create_payment
from ..warehouse.management import (
    deallocate_stock,
    deallocate_stock_for_order,
    decrease_stock,
    get_order_lines_with_track_inventory,
)
from ..warehouse.models import Stock
from . import (
    FulfillmentLineData,
    FulfillmentStatus,
    OrderOrigin,
    OrderStatus,
    events,
    utils,
)
from .events import (
    draft_order_created_from_replace_event,
    fulfillment_refunded_event,
    fulfillment_replaced_event,
    order_replacement_created,
    order_returned_event,
)
from .fetch import OrderLineInfo
from .models import Fulfillment, FulfillmentLine, Order, OrderLine
from .notifications import (
    send_fulfillment_confirmation_to_customer,
    send_order_canceled_confirmation,
    send_order_confirmed,
    send_order_refunded_confirmation,
    send_payment_confirmation,
)
from .utils import (
    order_line_needs_automatic_fulfillment,
    restock_fulfillment_lines,
    update_order_authorize_data,
    update_order_charge_data,
    update_order_status,
)

if TYPE_CHECKING:
    from ..app.models import App
    from ..plugins.manager import PluginsManager
    from ..site.models import SiteSettings
    from ..warehouse.models import Warehouse
    from .fetch import OrderInfo

logger = logging.getLogger(__name__)


OrderLineIDType = UUID
QuantityType = int


class OrderFulfillmentLineInfo(TypedDict):
    order_line: OrderLine
    quantity: int


def order_created(
    order_info: "OrderInfo",
    user: User,
    app: Optional["App"],
    manager: "PluginsManager",
    from_draft: bool = False,
    site_settings: Optional["SiteSettings"] = None,
):
    order = order_info.order
    events.order_created_event(order=order, user=user, app=app, from_draft=from_draft)
    call_event(manager.order_created, order)
    payment = order_info.payment
    if payment:
        if order.is_captured():
            order_captured(
                order_info=order_info,
                user=user,
                app=app,
                amount=payment.total,
                payment=payment,
                manager=manager,
                site_settings=site_settings,
            )
        elif order.is_pre_authorized():
            order_authorized(
                order=order,
                user=user,
                app=app,
                amount=payment.total,
                payment=payment,
                manager=manager,
            )
    channel = order_info.channel
    if channel.automatically_confirm_all_new_orders or from_draft:
        order_confirmed(order, user, app, manager)


def order_confirmed(
    order: "Order",
    user: User,
    app: Optional["App"],
    manager: "PluginsManager",
    send_confirmation_email: bool = False,
):
    """Order confirmed.

    Trigger event, plugin hooks and optionally confirmation email.
    """
    events.order_confirmed_event(order=order, user=user, app=app)
    call_event(manager.order_confirmed, order)
    if send_confirmation_email:
        send_order_confirmed(order, user, app, manager)


def handle_fully_paid_order(
    manager: "PluginsManager",
    order_info: "OrderInfo",
    user: Optional[User] = None,
    app: Optional["App"] = None,
    site_settings: Optional["SiteSettings"] = None,
):
    from ..giftcard.utils import fulfill_non_shippable_gift_cards

    order = order_info.order
    events.order_fully_paid_event(order=order, user=user, app=app)
    if order_info.customer_email:
        send_payment_confirmation(order_info, manager)
        if utils.order_needs_automatic_fulfillment(order_info.lines_data):
            automatically_fulfill_digital_lines(order_info, manager)
    try:
        analytics.report_order(order.tracking_client_id, order)
    except Exception:
        # Analytics failing should not abort the checkout flow
        logger.exception("Recording order in analytics failed")

    if site_settings is None:
        site_settings = Site.objects.get_current().settings

    if order_info.channel.automatically_fulfill_non_shippable_gift_card:
        order_lines = [line.line for line in order_info.lines_data]
        fulfill_non_shippable_gift_cards(
            order, order_lines, site_settings, user, app, manager
        )

    call_event(manager.order_fully_paid, order)
    call_event(manager.order_updated, order)


def cancel_order(
    order: "Order",
    user: Optional[User],
    app: Optional["App"],
    manager: "PluginsManager",
):
    """Cancel order.

    Release allocation of unfulfilled order items.
    """
    # transaction ensures proper allocation and event triggering
    with traced_atomic_transaction():
        events.order_canceled_event(order=order, user=user, app=app)
        deallocate_stock_for_order(order, manager)
        order.status = OrderStatus.CANCELED
        order.save(update_fields=["status", "updated_at"])

        call_event(manager.order_cancelled, order)
        call_event(manager.order_updated, order)

        call_event(send_order_canceled_confirmation, order, user, app, manager)


def order_refunded(
    order: "Order",
    user: Optional[User],
    app: Optional["App"],
    amount: "Decimal",
    payment: "Payment",
    manager: "PluginsManager",
):
    events.payment_refunded_event(
        order=order, user=user, app=app, amount=amount, payment=payment
    )
    call_event(manager.order_updated, order)

    send_order_refunded_confirmation(
        order, user, app, amount, payment.currency, manager
    )


def order_voided(
    order: "Order",
    user: Optional[User],
    app: Optional["App"],
    payment: "Payment",
    manager: "PluginsManager",
):
    events.payment_voided_event(order=order, user=user, app=app, payment=payment)
    call_event(manager.order_updated, order)


def order_returned(
    order: "Order",
    user: Optional[User],
    app: Optional["App"],
    returned_lines: List[Tuple[QuantityType, OrderLine]],
):
    order_returned_event(order=order, user=user, app=app, returned_lines=returned_lines)
    update_order_status(order)


def order_fulfilled(
    fulfillments: List[Fulfillment],
    user: Optional[User],
    app: Optional["App"],
    fulfillment_lines: List[FulfillmentLine],
    manager: "PluginsManager",
    gift_card_lines_info: List[GiftCardLineData],
    site_settings: "SiteSettings",
    notify_customer=True,
):
    from ..giftcard.utils import gift_cards_create

    order = fulfillments[0].order
    # transaction ensures webhooks are triggered only when order status and fulfillment
    # events are successfully created
    with traced_atomic_transaction():
        update_order_status(order)
        gift_cards_create(
            order,
            gift_card_lines_info,
            site_settings,
            user,
            app,
            manager,
        )
        events.fulfillment_fulfilled_items_event(
            order=order, user=user, app=app, fulfillment_lines=fulfillment_lines
        )
        call_event(manager.order_updated, order)

        for fulfillment in fulfillments:
            call_event(manager.fulfillment_created, fulfillment)

        if order.status == OrderStatus.FULFILLED:
            call_event(manager.order_fulfilled, order)
            for fulfillment in fulfillments:
                call_event(manager.fulfillment_approved, fulfillment)

    if notify_customer:
        for fulfillment in fulfillments:
            send_fulfillment_confirmation_to_customer(
                order, fulfillment, user, app, manager
            )


def order_awaits_fulfillment_approval(
    fulfillments: List[Fulfillment],
    user: Optional[User],
    app: Optional["App"],
    fulfillment_lines: List[FulfillmentLine],
    manager: "PluginsManager",
    _gift_card_lines: List["GiftCardLineData"],
    _site_settings: "SiteSettings",
    _notify_customer=True,
):
    order = fulfillments[0].order
    events.fulfillment_awaits_approval_event(
        order=order, user=user, app=app, fulfillment_lines=fulfillment_lines
    )
    call_event(manager.order_updated, order)


def order