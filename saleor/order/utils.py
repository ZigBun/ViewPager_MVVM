from decimal import Decimal
from functools import wraps
from typing import TYPE_CHECKING, Iterable, List, Optional, Tuple, cast

import graphene
from django.utils import timezone
from prices import Money, TaxedMoney

from ..account.models import User
from ..core.prices import quantize_price
from ..core.taxes import zero_money
from ..core.tracing import traced_atomic_transaction
from ..core.weight import zero_weight
from ..discount import OrderDiscountType
from ..discount.models import NotApplicable, OrderDiscount, Voucher, VoucherType
from ..discount.utils import (
    apply_discount_to_value,
    get_products_voucher_discount,
    get_sale_id_applied_as_a_discount,
    validate_voucher_in_order,
)
from ..giftcard import events as gift_card_events
from ..giftcard.models import GiftCard
from ..payment.model_helpers import get_total_authorized
from ..product.utils.digital_products import get_default_digital_content_settings
from ..shipping.interface import ShippingMethodData
from ..shipping.models import ShippingMethod, ShippingMethodChannelListing
from ..shipping.utils import (
    convert_to_shipping_method_data,
    initialize_shipping_method_active_status,
)
from ..tax.utils import (
    get_display_gross_prices,
    get_tax_class_kwargs_for_order_line,
    get_tax_country,
)
from ..warehouse.management import (
    decrease_allocations,
    get_order_lines_with_track_inventory,
    increase_allocations,
    increase_stock,
)
from ..warehouse.models import Warehouse
from . import (
    ORDER_EDITABLE_STATUS,
    FulfillmentStatus,
    OrderAuthorizeStatus,
    OrderChargeStatus,
    OrderStatus,
    events,
)
from .fetch import OrderLineInfo
from .models import Order, OrderLine

if TYPE_CHECKING:
    from ..app.models import App
    from ..channel.models import Channel
    from ..checkout.fetch import CheckoutInfo
    from ..plugins.manager import PluginsManager


def get_order_country(order: Order) -> str:
    """Return country to which order will be shipped."""
    address = order.billing_address
    if order.is_shipping_required():
        address = order.shipping_address
    if address is None:
        return order.channel.default_country.code
    return address.country.code


def order_line_needs_automatic_fulfillment(line_data: OrderLineInfo) -> bool:
    """Check if given line is digital and should be automatically fulfilled."""
    digital_content_settings = get_default_digital_content_settings()
    default_automatic_fulfillment = digital_content_settings["automatic_fulfillment"]
    content = line_data.digital_content
    if not content:
        return False
    if default_automatic_fulfillment and content.use_default_settings:
        return True
    if content.automatic_fulfillment:
        return True
    return False


def order_needs_automatic_fulfillment(lines_data: Iterable["OrderLineInfo"]) -> bool:
    """Check if order has digital products which should be automatically fulfilled."""
    for line_data in lines_data:
        if line_data.is_digital and order_line_needs_automatic_fulfillment(line_data):
            return True
    return False


def update_voucher_discount(func):
    """Recalculate order discount amount based on order voucher."""

    @wraps(func)
    def decorator(*args, **kwargs):
        if kwargs.pop("update_voucher_discount", True):
            order = args[0]
            try:
                discount = get_voucher_discount_for_order(order)
            except NotApplicable:
                discount = zero_money(order.currency)
        return func(*args, **kwargs, discount=discount)

    return decorator


def get_voucher_discount_assigned_to_order(order: Order):
    return order.discounts.filter(type=OrderDiscountType.VOUCHER).first()


def invalidate_order_prices(order: Order, *, save: bool = False) -> None:
    """Mark order as ready for prices recalculation.

    Does nothing if order is not editable
    (it's status is neither draft, nor unconfirmed).

    By default, no save to database is executed.
    Either manually call `order.save()` after, or pass `save=True`.
    """
    if order.status not in ORDER_EDITABLE_STATUS:
        return

    order.should_refresh_prices = True

    if save:
        order.save(update_fields=["should_refresh_prices"])


def recalculate_order_weight(order: Order, *, save: bool = False):
    """Recalculate order weights.

    By default, no save to database is executed.
    Either manually call `order.save()` after, or pass `save=True`.
    """
    weight = zero_weight()
    for line in order.lines.all():
        if line.variant:
            weight += line.variant.get_weight() * line.quantity
    weight.unit = order.weight.unit
    order.weight = weight
    if save:
        order.save(update_fields=["weight", "updated_at"])


def _calculate_quantity_including_returns(order):
    lines = list(order.lines.all())
    total_quantity = sum([line.quantity for line in lines])
    quantity_fulfilled = sum([line.quantity_fulfilled for line in lines])
    quantity_returned = 0
    quantity_replaced = 0
    for fulfillment in order.fulfillments.all():
        # count returned quantity for order
        if fulfillment.status in [
            FulfillmentStatus.RETURNED,
            FulfillmentStatus.REFUNDED_AND_RETURNED,
        ]:
            quantity_returned += fulfillment.get_total_quantity()
        # count replaced quantity for order
        elif fulfillment.status == FulfillmentStatus.REPLACED:
            quantity_replaced += fulfillment.get_total_quantity()

    # Subtract the replace quantity as it shouldn't be taken into consideration for
    # calculating the order status
    total_quantity -= quantity_replaced
    quantity_fulfilled -= quantity_replaced
    return total_quantity, quantity_fulfilled, quantity_returned


def update_order_status(order: Order):
    """Update order status depending on fulfillments."""
    (
        total_quantity,
        quantity_fulfilled,
        quantity_returned,
    ) = _calculate_quantity_including_returns(order)

    # check if order contains any fulfillments that awaiting approval
    awaiting_approval = order.fulfillments.filter(
        status=FulfillmentStatus.WAITING_FOR_APPROVAL
    ).exists()

    # total_quantity == 0 means that all products have been replaced, we don't change
    # the order status in that case
    if total_quantity == 0:
        status = order.status
    elif quantity_fulfilled <= 0:
        status = OrderStatus.UNFULFILLED
    elif 0 < quantity_returned < total_quantity:
        status = OrderStatus.PARTIALLY_RETURNED
    elif quantity_returned == total_quantity:
        status = OrderStatus.RETURNED
    elif quantity_fulfilled < total_quantity or awaiting_approval:
        status = OrderStatus.PARTIALLY_FULFILLED
    else:
        status = OrderStatus.FULFILLED

    if status != order.status:
        order.status = status
        order.save(update_fields=["status", "updated_at"])


@traced_atomic_transaction()
def create_order_line(
    order,
    line_data,
    manager,
    discounts=None,
    allocate_stock=False,
):
    channel = order.channel
    variant = line_data.variant
    quantity = line_data.quantity

    product = variant.product
    collections = product.collections.all()
    channel_listing = variant.channel_listings.get(channel=channel)

    # vouchers are not applied for new lines in unconfirmed/draft orders
    untaxed_unit_price = variant.get_price(
        product, collections, channel, channel_listing, discounts
    )
    if not discounts:
        untaxed_undiscounted_price = untaxed_unit_price
    else:
        untaxed_undiscounted_price = variant.get_price(
            product, collections, channel, channel_listing, []
        )
    unit_price = TaxedMoney(net=untaxed_unit_price, gross=untaxed_unit_price)
    undiscounted_unit_price = TaxedMoney(
        net=untaxed_undiscounted_price, gross=untaxed_undiscounted_price
    )
    total_price = unit_price * quantity
    undiscounted_total_price = undiscounted_unit_price * quantity

    tax_class = None
    if product.tax_class_id:
        tax_class = product.tax_class
    else:
        tax_class = product.product_type.tax_class

    product_name = str(product)
    variant_name = str(variant)
    translated_product_name = str(product.translated)
    translated_variant_name = str(variant.translated)
    if translated_product_name == product_name:
        translated_product_name = ""
    if translated_variant_name == variant_name:
        translated_variant_name = ""
    line = order.lines.create(
        product_name=product_name,
        variant_name=variant_name,
        translated_product_name=translated_product_name,
        translated_variant_name=translated_variant_name,
        product_sku=variant.sku,
        product_variant_id=variant.get_global_id(),
        is_shipping_required=variant.is_shipping_required(),
        is_gift_card=variant.is_gift_card(),
        quantity=quantity,
        unit_price=unit_price,
        undiscounted_unit_price=undiscounted_unit_price,
        base_unit_price=untaxed_unit_price,
        undiscounted_base_unit_price=untaxed_undiscounted_price,
        total_price=total_price,
        undiscounted_total_price=undiscounted_total_price,
        variant=variant,
        **get_tax_class_kwargs_for_order_line(tax_class),
    )

    unit_discount = line.undiscounted_unit_price - line.unit_price
    if unit_discount.gross:
        sale_id = get_sale_id_applied_as_a_discount(
            product=product,
            price=channel_listing.price,
            discounts=discounts,
            collections=collections,
            channel=channel,
            variant_id=variant.id,
        )

        tax_configuration = channel.tax_configuration
        prices_entered_with_tax = tax_configuration.prices_entered_with_tax

        if prices_entered_with_tax:
            discount_amount = unit_discount.gross
        else:
            discount_amount = unit_discount.net
        line.unit_discount = discount_amount
        line.unit_discount_value = discount_amount.amount
        line.unit_discount_reason = (
            f"Sale: {graphene.Node.to_global_id('Sale', sale_id)}"
        )
        line.sale_id = graphene.Node.to_global_id("Sale", sale_id) if sale_id else None

        line.save(
            update_fields=[
                "unit_discount_amount",
                "unit_discount_value",
                "unit_discount_reason",
                "sale_id",
            ]
        )

    if allocate_stock:
        increase_allocations(
            [
                OrderLineInfo(
                    line=line,
                    quantity=quantity,
                    variant=variant,
                    warehouse_pk=None,
                )
            ],
            channel,
            manager=manager,
        )

    return line


@traced_atomic_transaction()
def add_variant_to_order(
    order,
    line_data,
    user,
    app,
    manager,
    discounts=None,
    allocate_stock=False,
):
    """Add total_quantity of variant to order.

    Returns an order line the variant was added to.
    """
    channel = order.channel

    if line_data.line_id:
        line = order.lines.get(pk=line_data.line_id)
        old_quantity = line.quantity
        new_quantity = old_quantity + line_data.quantity
        line_info = OrderLineInfo(line=line, quantity=old_quantity)
        change_order_line_quantity(
            user,
            app,
            line_info,
            old_quantity,
            new_quantity,
            channel,
            manager=manager,
            send_event=False,
        )

        if allocate_stock:
            increase_allocations(
           