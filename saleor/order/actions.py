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


def order_authorized(
    order: "Order",
    user: Optional[User],
    app: Optional["App"],
    amount: "Decimal",
    payment: "Payment",
    manager: "PluginsManager",
):
    events.payment_authorized_event(
        order=order, user=user, app=app, amount=amount, payment=payment
    )
    call_event(manager.order_updated, order)


def order_captured(
    order_info: "OrderInfo",
    user: Optional[User],
    app: Optional["App"],
    amount: "Decimal",
    payment: "Payment",
    manager: "PluginsManager",
    site_settings: Optional["SiteSettings"] = None,
):
    order = order_info.order
    events.payment_captured_event(
        order=order, user=user, app=app, amount=amount, payment=payment
    )
    call_event(manager.order_updated, order)
    if order.is_fully_paid():
        handle_fully_paid_order(manager, order_info, user, app, site_settings)


def fulfillment_tracking_updated(
    fulfillment: Fulfillment,
    user: User,
    app: Optional["App"],
    tracking_number: str,
    manager: "PluginsManager",
):
    events.fulfillment_tracking_updated_event(
        order=fulfillment.order,
        user=user,
        app=app,
        tracking_number=tracking_number,
        fulfillment=fulfillment,
    )
    call_event(manager.tracking_number_updated, fulfillment)
    call_event(manager.order_updated, fulfillment.order)


def cancel_fulfillment(
    fulfillment: Fulfillment,
    user: User,
    app: Optional["App"],
    warehouse: Optional["Warehouse"],
    manager: "PluginsManager",
):
    """Cancel fulfillment.

    Return products to corresponding stocks if warehouse was defined.
    """
    with traced_atomic_transaction():
        fulfillment = Fulfillment.objects.select_for_update().get(pk=fulfillment.pk)
        events.fulfillment_canceled_event(
            order=fulfillment.order, user=user, app=app, fulfillment=fulfillment
        )
        if warehouse:
            restock_fulfillment_lines(fulfillment, warehouse)
            events.fulfillment_restocked_items_event(
                order=fulfillment.order,
                user=user,
                app=app,
                fulfillment=fulfillment,
                warehouse_pk=warehouse.pk,
            )
        fulfillment.status = FulfillmentStatus.CANCELED
        fulfillment.save(update_fields=["status"])
        update_order_status(fulfillment.order)
        call_event(manager.fulfillment_canceled, fulfillment)
        call_event(manager.order_updated, fulfillment.order)
    return fulfillment


def cancel_waiting_fulfillment(
    fulfillment: Fulfillment,
    user: User,
    app: Optional["App"],
    manager: "PluginsManager",
):
    """Cancel fulfillment which is in waiting for approval state."""
    fulfillment = Fulfillment.objects.get(pk=fulfillment.pk)
    # transaction ensures sending webhooks after order line is updated and events are
    # successfully created
    with traced_atomic_transaction():
        events.fulfillment_canceled_event(
            order=fulfillment.order, user=user, app=app, fulfillment=None
        )

        order_lines = []
        for line in fulfillment:
            order_line = line.order_line
            order_line.quantity_fulfilled -= line.quantity
            order_lines.append(order_line)
        OrderLine.objects.bulk_update(order_lines, ["quantity_fulfilled"])

        fulfillment.delete()
        update_order_status(fulfillment.order)
        call_event(manager.fulfillment_canceled, fulfillment)
        call_event(manager.order_updated, fulfillment.order)


def approve_fulfillment(
    fulfillment: Fulfillment,
    user: User,
    app: Optional["App"],
    manager: "PluginsManager",
    settings: "SiteSettings",
    notify_customer=True,
    allow_stock_to_be_exceeded: bool = False,
):
    from ..giftcard.utils import gift_cards_create

    with traced_atomic_transaction():
        fulfillment.status = FulfillmentStatus.FULFILLED
        fulfillment.save()
        order = fulfillment.order
        if notify_customer:
            send_fulfillment_confirmation_to_customer(
                fulfillment.order, fulfillment, user, app, manager
            )
        events.fulfillment_fulfilled_items_event(
            order=order,
            user=user,
            app=app,
            fulfillment_lines=list(fulfillment.lines.all()),
        )
        lines_to_fulfill = []
        gift_card_lines_info = []
        insufficient_stocks = []
        for fulfillment_line in fulfillment.lines.all().prefetch_related(
            "order_line__variant"
        ):
            order_line = fulfillment_line.order_line
            variant = fulfillment_line.order_line.variant

            stock = fulfillment_line.stock

            if stock is None:
                warehouse_pk = None
                if not allow_stock_to_be_exceeded:
                    error_data = InsufficientStockData(
                        variant=variant,
                        order_line=order_line,
                        warehouse_pk=warehouse_pk,
                        available_quantity=0,
                    )
                    insufficient_stocks.append(error_data)
            else:
                warehouse_pk = stock.warehouse_id

            lines_to_fulfill.append(
                OrderLineInfo(
                    line=order_line,
                    quantity=fulfillment_line.quantity,
                    variant=variant,
                    warehouse_pk=warehouse_pk,
                )
            )
            if order_line.is_gift_card:
                gift_card_lines_info.append(
                    GiftCardLineData(
                        quantity=fulfillment_line.quantity,
                        order_line=order_line,
                        variant=variant,
                        fulfillment_line=fulfillment_line,
                    )
                )

        if insufficient_stocks:
            raise InsufficientStock(insufficient_stocks)

        _decrease_stocks(lines_to_fulfill, manager, allow_stock_to_be_exceeded)
        order.refresh_from_db()
        update_order_status(order)

        call_event(manager.order_updated, order)
        call_event(manager.fulfillment_approved, fulfillment)
        if order.status == OrderStatus.FULFILLED:
            call_event(manager.order_fulfilled, order)

        if gift_card_lines_info:
            gift_cards_create(
                order,
                gift_card_lines_info,
                settings,
                user,
                app,
                manager,
            )

    return fulfillment


def mark_order_as_paid(
    order: "Order",
    request_user: User,
    app: Optional["App"],
    manager: "PluginsManager",
    external_reference: Optional[str] = None,
):
    """Mark order as paid.

    Allows to create a payment for an order without actually performing any
    payment by the gateway.
    """
    # transaction ensures that webhooks are triggered when payments and transactions are
    # properly created
    with traced_atomic_transaction():
        payment = create_payment(
            gateway=CustomPaymentChoices.MANUAL,
            payment_token="",
            currency=order.total.gross.currency,
            email=order.user_email,
            total=order.total.gross.amount,
            order=order,
            external_reference=external_reference,
        )
        payment.charge_status = ChargeStatus.FULLY_CHARGED
        payment.captured_amount = order.total.gross.amount
        payment.save(update_fields=["captured_amount", "charge_status", "modified_at"])

        Transaction.objects.create(
            payment=payment,
            action_required=False,
            kind=TransactionKind.EXTERNAL,
            token=external_reference or "",
            is_success=True,
            amount=order.total.gross.amount,
            currency=order.total.gross.currency,
            gateway_response={},
        )
        events.order_manually_marked_as_paid_event(
            order=order,
            user=request_user,
            app=app,
            transaction_reference=external_reference,
        )

        call_event(manager.order_fully_paid, order)
        call_event(manager.order_updated, order)

        update_order_charge_data(
            order,
        )
        update_order_authorize_data(
            order,
        )


def clean_mark_order_as_paid(order: "Order"):
    """Check if an order can be marked as paid."""
    if order.payments.exists():
        raise PaymentError(
            "Orders with payments can not be manually marked as paid.",
        )


def _decrease_stocks(order_lines_info, manager, allow_stock_to_be_exceeded=False):
    lines_to_decrease_stock = get_order_lines_with_track_inventory(order_lines_info)
    if lines_to_decrease_stock:
        decrease_stock(
            lines_to_decrease_stock,
            manager,
            allow_stock_to_be_exceeded=allow_stock_to_be_exceeded,
        )


def _increase_order_line_quantity(order_lines_info):
    order_lines = []
    for line_info in order_lines_info:
        line = line_info.line
        line.quantity_fulfilled += line_info.quantity
        order_lines.append(line)

    OrderLine.objects.bulk_update(order_lines, ["quantity_fulfilled"])


def fulfill_order_lines(
    order_lines_info: Iterable["OrderLineInfo"],
    manager: "PluginsManager",
    allow_stock_to_be_exceeded: bool = False,
):
    """Fulfill order line with given quantity."""
    # transaction ensures that there is a consistency between quantities in order line
    # and stocks
    with traced_atomic_transaction():
        _decrease_stocks(order_lines_info, manager, allow_stock_to_be_exceeded)
        _increase_order_line_quantity(order_lines_info)


def automatically_fulfill_digital_lines(
    order_info: "OrderInfo", manager: "PluginsManager"
):
    """Fulfill all digital lines which have enabled automatic fulfillment setting.

    Send confirmation email afterward.
    """
    order = order_info.order
    digital_lines_data = [
        line_data
        for line_data in order_info.lines_data
        if not line_data.line.is_shipping_required and line_data.digital_content
    ]
    # transaction ensures fulfillment consistency
    with traced_atomic_transaction():
        if not digital_lines_data:
            return
        fulfillment, _ = Fulfillment.objects.get_or_create(order=order)

        fulfillments = []
        lines_info = []
        for line_data in digital_lines_data:
            if not order_line_needs_automatic_fulfillment(line_data):
                continue
            digital_content = line_data.digital_content
            line = line_data.line
            if digital_content:
                digital_content.urls.create(line=line)
            quantity = line_data.quantity
            fulfillments.append(
                FulfillmentLine(
                    fulfillment=fulfillment, order_line=line, quantity=quantity
                )
            )
            allocation = line.allocations.first()
            if allocation:
                line_data.warehouse_pk = allocation.stock.warehouse.pk
            else:
                # allocation is not created when track inventory for given product
                # is turned off so it doesn't matter which warehouse we'll use
                if line_data.variant:
                    stock = line_data.variant.stocks.first()
                    if stock:
                        line_data.warehouse_pk = stock.warehouse.pk

            lines_info.append(line_data)

        FulfillmentLine.objects.bulk_create(fulfillments)
        fulfill_order_lines(lines_info, manager)

        send_fulfillment_confirmation_to_customer(
            order, fulfillment, user=order.user, app=None, manager=manager
        )
        update_order_status(order)


def _create_fulfillment_lines(
    fulfillment: Fulfillment,
    warehouse_pk: UUID,
    lines_data: List[OrderFulfillmentLineInfo],
    channel_slug: str,
    gift_card_lines_info: List[GiftCardLineData],
    manager: "PluginsManager",
    decrease_stock: bool = True,
    allow_stock_to_be_exceeded: bool = False,
) -> List[FulfillmentLine]:
    """Modify stocks and allocations. Return list of unsaved FulfillmentLines.

    Args:
        fulfillment (Fulfillment): Fulfillment to create lines
        warehouse_pk (str): Warehouse to fulfill order.
        lines_data (List[Dict]): List with information from which system
            create FulfillmentLines. Example:
                [
                    {
                        "order_line": (OrderLine),
                        "quantity": (int),
                    },
                    ...
                ]
        channel_slug (str): Channel for which fulfillment lines should be created.
        gift_card_lines_info (List): List with information required
            to create gift cards.
        manager (PluginsManager): Plugin manager from given context
        decrease_stock (Bool): Stocks will get decreased if this is True.
        allow_stock_to_be_exceeded (bool): If `True` then stock quantity could exceed.
            Default value is set to `False`.

    Return:
        List[FulfillmentLine]: Unsaved fulfillmet lines created for this fulfillment
            based on information form `lines`

    Raise:
        InsufficientStock: If system hasn't containt enough item in stock for any line.

    """
    lines = [line_data["order_line"] for line_data in lines_data]
    variants = [line.variant for line in lines if line.variant]
    stocks = (
        Stock.objects.for_channel_and_country(channel_slug)
        .filter(warehouse_id=warehouse_pk, product_variant__in=variants)
        .select_related("product_variant")
    )

    variant_to_stock: Dict[int, List[Stock]] = defaultdict(list)
    for stock in stocks:
        variant_to_stock[stock.product_variant_id].append(stock)

    insufficient_stocks = []
    fulfillment_lines = []
    lines_info = []
    for line in lines_data:
        quantity = line["quantity"]
        order_line = line["order_line"]
        if quantity > 0:
            variant = order_line.variant
            stock = None
            if variant:
                line_stocks = variant_to_stock.get(variant.id)
                stock = line_stocks[0] if line_stocks else None

            # If there is no stock but allow_stock_to_be_exceeded == True
            # we proceed with fulfilling the order, treat as error otherwise
            if stock is None and not allow_stock_to_be_exceeded:
                error_data = InsufficientStockData(
                    variant=variant,
                    order_line=order_line,
                    warehouse_pk=warehouse_pk,
                    available_quantity=0,
                )
                insufficient_stocks.append(error_data)
                continue

            is_digital = order_line.is_digital
            lines_info.append(
                OrderLineInfo(
                    line=order_line,
                    is_digital=is_digital,
                    quantity=quantity,
                    variant=variant,
                    warehouse_pk=warehouse_pk,
                )
            )
            if variant and is_digital:
                variant.digital_content.urls.create(line=order_line)
            fulfillment_l