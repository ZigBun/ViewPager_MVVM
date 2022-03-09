from typing import TYPE_CHECKING, Iterable

from prices import Money, TaxedMoney

from ..core.taxes import zero_money
from ..discount import DiscountValueType, OrderDiscountType
from ..discount.models import OrderDiscount
from ..discount.utils import apply_discount_to_value
from .interface import OrderTaxedPricesData

if TYPE_CHECKING:
    from .models import Order, OrderLine


# We need this function to don't break Avalara Excise.
def base_order_shipping(order: "Order") -> Money:
    return order.base_shipping_price


def _base_order_subtotal(order: "Order", lines: Iterable["OrderLine"]) -> Money:
    currency = order.currency
    subtotal = zero_money(currency)
    for line in lines:
        quantity = line.quantity
        price_with_discounts = line.base_unit_price * quantity
        subtotal += price_with_discounts
    return subtotal


def base_order_total(order: "Order", lines: Iterable["OrderLine"]) -> Money:
    """Return order total, recalculate, and update order discounts.

    This function returns the order total. All discounts are included in this price.
    Shipping vouchers are included in the shipping price.
    Specific product vouchers are included in line base prices.
    Entire order vouchers are recalculated and updated in this function
    (OrderDiscounts with type `order_discount.type == OrderDiscountType.VOUCHER`).
    Staff order discounts are recalculated and updated in this function
    (OrderDiscounts with type `order_discount.type == OrderDiscountType.MANUAL`).
    """
    currency = order.currency
    subtotal = _base_order_subtotal(order, lines)
    shipping_price = order.base_shipping_price
    order_discounts = order.discounts.all()
    order_discounts_to_update = []
    for order_discount in order_discounts:
        subtotal_before_discount = subtotal
        shipping_price_before_discount = shipping_price
        if order_discount.type == OrderDiscountType.VOUCHER:
            subtotal = apply_discount_to_value(
                value=order_discount.value,
                value_type=order_discount.value_type,
                currency=currency,
                price_to_discount=subtotal,
            )
        elif order_discount.value_type == DiscountValueType.PERCENTAGE:
            subtotal = apply_discount_to_value(
                value=order_discount.value,
                value_type=order_discount.value_type,
                currency=currency,
                price_to_discount=subtotal,