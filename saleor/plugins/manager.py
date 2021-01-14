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
            self.__run_me