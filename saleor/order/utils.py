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
    (it's status is neither draft