from collections import defaultdict
from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

import opentracing
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.utils.module_loading import import_string
from graphene import Mutation
from graphql import GraphQLError
from graphql.execution import ExecutionResult
from prices import TaxedMoney

from ..channel.models import Channel
from ..checkout import base_calculations
from ..core.models import EventDelivery
from ..core.payments import PaymentInterface
from ..core.prices import quantize_price
from ..core.taxes import TaxData, TaxType, zero_money, zero_taxed_money
from ..discount import DiscountInfo
from ..graphql.core import ResolveInfo, SaleorContext
from ..order import base_calculations as base_order_calculations
from ..order.interface import OrderTaxedPricesData
from ..tax.utils import calculate_tax_rate
from .base_plugin import ExcludedShippingMethod, ExternalAccessTokens
from .models import PluginConfiguration

if TYPE_CHECKING:
    from ..account.models import Address, Group, User
    from ..app.models import App
    from ..attribute.models import Attribute, AttributeValue
    from ..checkout.fetch import CheckoutInfo, CheckoutLineInfo
    from ..checkout.models import Checkout
    from ..core.middleware import Requestor
    from ..discount.models import Sale, Voucher
    from ..giftcard.models import GiftCard
    from ..invoice.models import Invoice
    from ..menu.models import Menu, MenuItem
    from ..order.models import Fulfillment, Order, OrderLine
    from ..page.models import Page, PageType
    from ..payment.interface import (
        CustomerSource,
        GatewayResponse,
        InitializedPaymentResponse,
        PaymentData,
        PaymentGateway,
        TokenConfig,
        TransactionActionData,
    )
    from ..payment.models import TransactionItem
    from ..product.models import (
        Category,
        Collection,
        Product,
        ProductMedia,
        ProductType,
        ProductVariant,
    )
    from ..shipping.interface import ShippingMethodData
    from ..shipping.models import ShippingMethod, ShippingZone
    from ..tax.models import TaxClass
    from ..thumbnail.models import Thumbnail
    from ..translation.models import Translation
    from ..warehouse.models import Stock, Warehouse
    from .base_plugin import BasePlugin

NotifyEventTypeChoice = str


class PluginsManager(PaymentInterface):
    """Base manager for handling plugins logic."""

    plugins_per_channel: Dict[str, List["BasePlugin"]] = {}
    global_plugins: List["BasePlugin"] = []
    all_plugins: List["BasePlugin"] = []

    def _load_plugin(
        self,
        PluginClass: Type["BasePlugin"],
        db_configs_map: dict,
        channel: Optional["Channel"] = None,
        requestor_getter=None,
        allow_replica=True,
    ) -> "BasePlugin":
        db_config = None
        if PluginClass.PLUGIN_ID in db_configs_map:
            db_config = db_configs_map[PluginClass.PLUGIN_ID]
            plugin_config = db_config.configuration
            active = db_config.active
            channel = db_config.channel
        else:
            plugin_config = PluginClass.DEFAULT_CONFIGURATION
            active = PluginClass.get_default_active()

        return PluginClass(
            configuration=plugin_config,
            active=active,
            channel=channel,
            requestor_getter=requestor_getter,
            db_config=db_config,
            allow_replica=allow_replica,
        )

    def __init__(self, plugins: List[str], requestor_getter=None, allow_replica=True):
        with opentracing.global_tracer().start_active_span("PluginsManager.__init__"):
            self.all_plugins = []
            self.global_plugins = []
            self.plugins_per_channel = defaultdict(list)

            global_db_configs, channel_db_configs = self._get_db_plugin_configs()
            channels = Channel.objects.all()

            for plugin_path in plugins:
                with opentracing.global_tracer().start_active_span(f"{plugin_path}"):
                    PluginClass = import_string(plugin_path)
                    if not getattr(PluginClass, "CONFIGURATION_PER_CHANNEL", False):
                        plugin = self._load_plugin(
                            PluginClass,
                            global_db_configs,
                            requestor_getter=requestor_getter,
                            allow_replica=allow_replica,
                        )
                        self.global_plugins.append(plugin)
                        self.all_plugins.append(plugin)
                    else:
                        for channel in channels:
                            channel_configs = channel_db_configs.get(channel, {})
                            plugin = self._load_plugin(
                                PluginClass,
                                channel_configs,
                                channel,
                                requestor_getter,
                                allow_replica,
                            )
                            self.plugins_per_channel[channel.slug].append(plugin)
                            self.all_plugins.append(plugin)

            for channel in channels:
                self.plugins_per_channel[channel.slug].extend(self.global_plugins)

    def _get_db_plugin_configs(self):
        with opentracing.global_tracer().start_active_span("_get_db_plugin_configs"):
            qs = (
                PluginConfiguration.objects.all()
                .using(settings.DATABASE_CONNECTION_REPLICA_NAME)
                .prefetch_related("channel")
            )
            channel_configs: DefaultDict[Channel, Dict] = defaultdict(dict)
            global_configs = {}
            for db_plugin_config in qs:
                channel = db_plugin_config.channel
                if channel is None:
                    global_configs[db_plugin_config.identifier] = db_plugin_config
                else:
                    channel_configs[channel][
                        db_plugin_config.identifier
                    ] = db_plugin_config
            return global_configs, channel_configs

    def __run_method_on_plugins(
        self,
        method_name: str,
        default_value: Any,
        *args,
        channel_slug: Optional[str] = None,
        **kwargs
    ):
        """Try to run a method with the given name on each declared active plugin."""
        value = default_value
        plugins = self.get_plugins(channel_slug=channel_slug, active_only=True)
        for plugin in plugins:
            value = self.__run_method_on_single_plugin(
                plugin, method_name, value, *args, **kwargs
            )
        return value

    def __run_method_on_single_plugin(
        self,
        plugin: Optional["BasePlugin"],
        method_name: str,
        previous_value: Any,
        *args,
        **kwargs,
    ) -> Any:
        """Run method_name on plugin.

        Method will return value returned from plugin's
        method. If plugin doesn't have own implementation of expected method_name, it
        will return previous_value.
        """
        plugin_method = getattr(plugin, method_name, NotImplemented)
        if plugin_method == NotImplemented:
            return previous_value
        returned_value = plugin_method(
            *args, **kwargs, previous_value=previous_value
        )  # type:ignore
        if returned_value == NotImplemented:
            return previous_value
        return returned_value

    def check_payment_balance(self, details: dict, channel_slug: str) -> dict:
        return self.__run_method_on_plugins(
            "check_payment_balance", None, details, channel_slug=channel_slug
        )

    def change_user_address(
        self, address: "Address", address_type: Optional[str], user: Optional["User"]
    ) -> "Address":
        default_value = address
        return self.__run_method_on_plugins(
            "change_user_address", default_value, address, address_type, user
        )

    def calculate_checkout_total(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        address: Optional["Address"],
        discounts: Iterable[DiscountInfo],
    ) -> TaxedMoney:
        currency = checkout_info.checkout.currency

        default_value = base_calculations.checkout_total(
            checkout_info,
            discounts,
            lines,
        )
        taxed_default_value = TaxedMoney(net=default_value, gross=default_value)

        if default_value <= zero_money(currency):
            return quantize_price(
                taxed_default_value,
                currency,
            )

        return quantize_price(
            self.__run_method_on_plugins(
                "calculate_checkout_total",
                taxed_default_value,
                checkout_info,
                lines,
                address,
                discounts,
                channel_slug=checkout_info.channel.slug,
            ),
            currency,
        )

    def calculate_checkout_subtotal(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        address: Optional["Address"],
        discounts: Iterable[DiscountInfo],
    ) -> TaxedMoney:
        line_totals = [
            self.calculate_checkout_line_total(
                checkout_info,
                lines,
                line_info,
                address,
                discounts,
            )
            for line_info in lines
        ]
        currency = checkout_info.checkout.currency
        total = sum(line_totals, zero_taxed_money(currency))
        return quantize_price(
            total,
            currency,
        )

    def calculate_checkout_shipping(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        address: Optional["Address"],
        discounts: Iterable[DiscountInfo],
    ) -> TaxedMoney:
        price = base_calculations.base_checkout_delivery_price(checkout_info, lines)
        default_value = TaxedMoney(price, price)
        return quantize_price(
            self.__run_method_on_plugins(
                "calculate_checkout_shipping",
                default_value,
                checkout_info,
                lines,
                address,
                discounts,
                channel_slug=checkout_info.channel.slug,
            ),
            checkout_info.checkout.currency,
        )

    def calculate_order_total(
        self,
        order: "Order",
        lines: Iterable["OrderLine"],
    ) -> TaxedMoney:
        currency = order.currency
        default_value = base_order_calculations.base_order_total(order, lines)
        default_value = TaxedMoney(default_value, default_value)
        if default_value <= zero_taxed_money(currency):
            return quantize_price(
                default_value,
                currency,
            )

        return quantize_price(
            self.__run_method_on_plugins(
                "calculate_order_total",
                default_value,
                order,
                lines,
                channel_slug=order.channel.slug,
            ),
            currency,
        )

    def calculate_order_shipping(self, order: "Order") -> TaxedMoney:
        shipping_price = order.base_shipping_price
        default_value = quantize_price(
            TaxedMoney(net=shipping_price, gross=shipping_price),
            shipping_price.currency,
        )
        return quantize_price(
            self.__run_method_on_plugins(
                "calculate_order_shipping",
                default_value,
                order,
                channel_slug=order.channel.slug,
            ),
            order.currency,
        )

    def get_checkout_shipping_tax_rate(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        address: Optional["Address"],
        discounts: Iterable[DiscountInfo],
        shipping_price: TaxedMoney,
    ):
        default_value = calculate_tax_rate(shipping_price)
        return self.__run_method_on_plugins(
            "get_checkout_shipping_tax_rate",
            default_value,
            checkout_info,
            lines,
            address,
            discounts,
            channel_slug=checkout_info.channel.slug,
        ).quantize(Decimal(".0001"))

    def get_order_shipping_tax_rate(self, order: "Order", shipping_price: TaxedMoney):
        default_value = calculate_tax_rate(shipping_price)
        return self.__run_method_on_plugins(
            "get_order_shipping_tax_rate",
            default_value,
            order,
            channel_slug=order.channel.slug,
        ).quantize(Decimal(".0001"))

    def calculate_checkout_line_total(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        checkout_line_info: "CheckoutLineInfo",
        address: Optional["Address"],
        discounts: Iterable["DiscountInfo"],
    ) -> TaxedMoney:
        default_value = base_calculations.calculate_base_line_total_price(
            checkout_line_info,
            checkout_info.channel,
            discounts,
        )
        # apply entire order discount
        default_value = base_calculations.apply_checkout_discount_on_checkout_line(
            checkout_info,
            lines,
            checkout_line_info,
            discounts,
            default_value,
        )
        default_value = quantize_price(default_value, checkout_info.checkout.currency)
        default_taxed_value = TaxedMoney(net=default_value, gross=default_value)
        line_total = self.__run_method_on_plugins(
            "calculate_checkout_line_total",
            default_taxed_value,
            checkout_info,
            lines,
            checkout_line_info,
            address,
            discounts,
            channel_slug=checkout_info.channel.slug,
        )

        return quantize_price(line_total, checkout_info.checkout.currency)

    def calculate_order_line_total(
        self,
        order: "Order",
        order_line: "OrderLine",
        variant: "ProductVariant",
        product: "Product",
    ) -> OrderTaxedPricesData:
        default_value = base_order_calculations.base_order_line_total(order_line)
        currency = order_line.currency

        line_total = self.__run_method_on_plugins(
            "calculate_order_line_total",
            default_value,
            order,
            order_line,
            variant,
            product,
            channel_slug=order.channel.slug,
        )

        line_total.price_with_discounts = quantize_price(
            line_total.price_with_discounts, currency
        )
        line_total.undiscounted_price = quantize_price(
            line_total.undiscounted_price, currency
        )
        return line_total

    def calculate_checkout_line_unit_price(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        checkout_line_info: "CheckoutLineInfo",
        address: Optional["Address"],
        discounts: Iterable["DiscountInfo"],
    ) -> TaxedMoney:
        quantity = checkout_line_info.line.quantity
        default_value = base_calculations.calculate_base_line_unit_price(
            checkout_line_info, checkout_info.channel, discounts
        )
        # apply entire order discount
        total_value = base_calculations.apply_checkout_discount_on_checkout_line(
            checkout_info,
            lines,
            checkout_line_info,
            discounts,
            default_value * quantity,
        )
        default_taxed_value = TaxedMoney(
            net=total_value / quantity, gross=default_value
        )
        unit_price = self.__run_method_on_plugins(
            "calculate_checkout_line_unit_price",
            default_taxed_value,
            checkout_info,
            lines,
            checkout_line_info,
            address,
            discounts,
            channel_slug=checkout_info.channel.slug,
        )
        return quantize_price(unit_price, checkout_info.checkout.currency)

    def calculate_order_line_unit(
        self,
        order: "Order",
        order_line: "OrderLine",
        variant: "ProductVariant",
        product: "Product",
    ) -> OrderTaxedPricesData:
        default_value = OrderTaxedPricesData(
            undiscounted_price=TaxedMoney(
                order_line.undiscounted_base_unit_price,
                order_line.undiscounted_base_unit_price,
            ),
            price_with_discounts=TaxedMoney(
                order_line.base_unit_price,
                order_line.base_unit_price,
            ),
        )
        currency = order_line.currency
        line_unit = self.__run_method_on_plugins(
            "calculate_order_line_unit",
            default_value,
            order,
            order_line,
            variant,
            product,
            channel_slug=order.channel.slug,
        )
        line_unit.price_with_discounts = quantize_price(
            line_unit.price_with_discounts, currency
        )
        line_unit.undiscounted_price = quantize_price(
            line_unit.undiscounted_price, currency
        )
        return line_unit

    def get_checkout_line_tax_rate(
        self,
        checkout_info: "CheckoutInfo",
        lines: Iterable["CheckoutLineInfo"],
        checkout_line_info: "CheckoutLineInfo",
        address: Optional["Address"],
        discounts: Iterable[DiscountInfo],
        unit_price: TaxedMoney,
    ) -> Decimal:
        default_value = calculate_tax_rate(unit_price)
        return self.__run_method_on_plugins(
            "get_checkout_line_tax_rate",
            default_value,
            checkout_info,
            lines,
            checkout_line_info,
            address,
            discounts,
            channel_slug=checkout_info.channel.slug,
        ).quantize(Decimal(".0001"))

    def get_order_line_tax_rate(
        self,
        order: "Order",
        product: "Product",
        variant: "ProductVariant",
        address: Optional["Address"],
        unit_price: TaxedMoney,
    ) -> Decimal:
        default_value = calculate_tax_rate(unit_price)
        return self.__run_method_on_plugins(
            "get_order_line_tax_rate",
            default_value,
            order,
            product,
            variant,
            address,
            channel_slug=order.channel.slug,
        ).quantize(Decimal(".0001"))

    def get_tax_rate_type_choices(self) -> List[TaxType]:
        default_value: list = []
        return self.__run_method_on_plugins("get_tax_rate_type_choices", default_value)

    def show_taxes_on_storefront(self) -> bool:
        default_value = False
        return self.__run_method_on_plugins("show_taxes_on_storefront", default_value)

    def get_taxes_for_checkout(self, checkout_info, lines) -> Optional[TaxData]:
        return self.__run_plugin_method_until_first_success(
            "get_taxes_for_checkout",
            checkout_info,
            lines,
            channel_slug=checkout_info.channel.slug,
        )

    def get_taxes_for_order(self, order: "Order") -> Optional[TaxData]:
        return self.__run_plugin_method_until_first_success(
            "get_taxes_for_order", order, channel_slug=order.channel.slug
        )

    def preprocess_order_creation(
        self,
        checkout_info: "CheckoutInfo",
        discounts: Iterable[DiscountInfo],
        lines: Optional[Iterable["CheckoutLineInfo"]] = None,
    ):
        default_value = None
        return self.__run_method_on_plugins(
            "preprocess_order_creation",
            default_value,
            checkout_info,
            discounts,
            lines,
            channel_slug=checkout_info.channel.slug,
        )

    def customer_created(self, customer: "User"):
        default_value = None
        return self.__run_method_on_plugins("customer_created", default_value, customer)

    def customer_deleted(self, customer: "User"):
        default_value = None
        return self.__run_method_on_plugins("customer_deleted", default_value, customer)

    def customer_updated(self, customer: "User"):
        default_value = None
        return self.__run_method_on_plugins("customer_updated", default_value, customer)

    def customer_metadata_updated(self, customer: "User"):
        default_value = None
        return self.__run_method_on_plugins(
            "customer_metadata_updated", default_value, customer
        )

    def collection_created(self, collection: "Collection"):
        default_value = None
        return self.__run_method_on_plugins(
            "collection_created", default_value, collection
        )

    def collection_updated(self, collection: "Collection"):
        default_value = None
        return self.__run_method_on_plugins(
            "collection_updated", default_value, collection
        )

    def collection_deleted(self, collection: "Collection"):
        default_value = None
        return self.__run_method_on_plugins(
            "collection_deleted", default_value, collection
        )

    def collection_metadata_updated(self, collection: "Collection"):
        default_value = None
        return self.__run_method_on_plugins(
            "collection_metadata_updated", default_value, collection
        )

    def product_created(self, product: "Product"):
        default_value = None
        return self.__run_method_on_plugins("product_created", default_value, product)

    def product_updated(self, product: "Product"):
        default_value = None
        return self.__run_method_on_plugins("product_updated", default_value, product)

    def product_deleted(self, product: "Product", variants: List[int]):
        default_value = None
        return self.__run_method_on_plugins(
            "product_deleted", default_value, product, variants
        )

    def product_media_created(self, media: "ProductMedia"):
        default_value = None
        return self.__run_method_on_plugins(
            "product_media_created", default_value, media
        )

    def product_media_updated(self, media: "ProductMedia"):
        default_value = None
        return self.__run_method_on_plugins(
            "product_media_updated", default_value, media
        )

    def product_media_deleted(self, media: "ProductMedia"):
        default_value = None
        return self.__run_method_on_plugins(
            "product_media_deleted", default_value, media
        )

    def product_metadata_updated(self, product: "Product"):
        default_value = None
        return self.__run_method_on_plugins(
            "product_metadata_updated", default_value, product
        )

    def product_variant_created(self, product_variant: "ProductVariant"):
        default_value = None
        return self.__run_method_on_plugins(
            "product_variant_created", default_value, product_variant
        )

    def product_variant_updated(self, product_variant: "ProductVariant"):
        default_value = None
        return self.__run_method_on_plugins(
            "product_variant_updated", default_value, product_variant
        )

    def product_variant_deleted(self, product_variant: "ProductVariant"):
        default_value = None
        return self.__run_method_on_plugins(
            "product_variant_deleted",
            default_value,
            product_variant,
        )

    def product_variant_out_of_stock(self, stock: "Stock"):
        default_value = None
        self.__run_method_on_plugins(
            "product_variant_out_of_stock", default_value, stock
        )

    def product_variant_back_in_stock(self, stock: "Stock"):
      