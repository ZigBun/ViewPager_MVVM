from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Any,
    DefaultDict,
    Iterable,
    Optional,
    Set,
    Tuple,
    Union,
)

from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from graphene import Mutation
from graphql import GraphQLError, ResolveInfo
from graphql.execution import ExecutionResult
from prices import Money, TaxedMoney

from ...account.models import User
from ...core.taxes import TaxData, TaxLineData, TaxType
from ...order.interface import OrderTaxedPricesData
from ..base_plugin import BasePlugin, ConfigurationTypeField, ExternalAccessTokens

if TYPE_CHECKING:
    from ...account.models import Address
    from ...checkout.fetch import CheckoutInfo, CheckoutLineInfo
    from ...checkout.models import Checkout
    from ...core.models import EventDelivery
    from ...discount import DiscountInfo
    from ...discount.models import Sale
    from ...order.models import Order, OrderLine
    from ...product.models import Product, ProductVariant


def sample_tax_data(obj_with_lines: Union["Order", "Checkout"]) -> TaxData:
    unit = Decimal("10.00")
    unit_gross = Decimal("12.30")
    lines = [
        TaxLineData(
            total_net_amount=unit * 3,
            total_gross_amount=unit_gross * 3,
            tax_rate=Decimal("23"),
        )
        for _ in obj_with_lines.lines.all()
    ]

    shipping = Decimal("50.00")
    shipping_gross = Decimal("63.20")

    return TaxData(
        shipping_price_net_amount=shipping,
        shipping_price_gross_amount=shipping_gross,
        shipping_tax_rate=Decimal("23"),
        lines=lines,
    )


class PluginSample(BasePlugin):
    PLUGIN_ID = "plugin.sample"
    PLUGIN_NAME = "PluginSample"
    PLUGIN_DESCRIPTION = "Test plugin description"
    DEFAULT_ACTIVE = True
    CONFIGURATION_PER_CHANNEL = False
    DEFAULT_CONFIGURATION = [
        {"name": "Username", "value": "admin"},
        {"name": "Password", "value": None},
        {"name": "Use sandbox", "value": False},
        {"name": "API private key", "value": None},
    ]

    CONFIG_STRUCTURE = {
        "Username": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Username input field",
            "label": "Username",
        },
        "Password": {
            "type": ConfigurationTypeField.PASSWORD,
            "help_text": "Password input field",
            "label": "Password",
        },
        "Use sandbox": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Use sandbox",
            "label": "Use sandbox",
        },
        "API private key": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "API key",
            "label": "Private key",
        },
        "certificate": {
            "type": ConfigurationTypeField.SECRET_MULTILINE,
            "help_text": "",
            "label": "Multiline certificate",
        },
    }

    def webhook(self, request: WSGIRequest, path: str, previous_value) -> HttpResponse:
        if path == "/webhook/paid":
            return JsonResponse(data={"received": True, "paid": True})
        if path == "/webhook/failed":
            return JsonResponse(data={"received": True, "paid": False})
        return HttpResponseNotFound()

    def calculate_checkout_total(
        self, checkout_info, lines, address, discounts, previous_value
    ):
        total = Money("1.0", currency=checkout_info.checkout.currency)
        return TaxedMoney(total, total)

    def calculate_checkout_shipping(
        self, checkout_info, lines, address, discounts, previous_value
    ):
        price = Money("1.0", currency=checkout_info.checkout.currency)
        return TaxedMoney(price, price)

    def calculate_order_shipping(self, order, previous_value):
        price = Money("1.0", currency=order.currency)
        return TaxedMoney(price, price)

    def calculate_checkout_line_total(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        checkout_line_info: "CheckoutLineInfo",
        address: Optional["Address"],
        discounts: Iterable["DiscountInfo"],
        previous_value: TaxedMoney,
    ):
        # See if delivery method doesn't trigger infinite recursion
        bool(checkout_info.delivery_method_info.delivery_method)

        price = Money("1.0", currency=checkout_info.checkout.currency)
        return TaxedMoney(price, price)

    def calculate_order_line_total(
        self,
        order: "Order",
        order_line: "OrderLine",
        variant: "ProductVariant",
        product: "Product",
        previous_value: OrderTaxedPricesData,
    ) -> OrderTaxedPricesData:
        price = Money("1.0", currency=order.currency)
        return OrderTaxedPricesData(
            price_with_discounts=TaxedMoney(price, price),
            undiscounted_price=TaxedMoney(price, price),
        )

    def calculate_checkout_line_unit_price(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        checkout_line_info: "CheckoutLineInfo",
        address: Optional["Address"],
        discounts: Iterable["DiscountInfo"],
        previous_value: TaxedMoney,
    ):
        currency = checkout_info.checkout.currency
        price = Money("10.0", currency)
        return TaxedMoney(price, price)

    def calculate_order_line_unit(
        self,
        order: "Order",
        order_line: "OrderLine",
        variant: "ProductVariant",
        product: "Product",
        previous_value: OrderTaxedPricesData,
    ):
        currency = order_line.unit_price.currency
        price = Money("1.0", currency)
        return OrderTaxedPricesData(
        