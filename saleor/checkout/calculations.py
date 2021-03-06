from decimal import Decimal
from typing import TYPE_CHECKING, Iterable, Optional, Tuple

from django.conf import settings
from django.utils import timezone
from prices import Money, TaxedMoney

from ..checkout import base_calculations
from ..core.prices import quantize_price
from ..core.taxes import TaxData, zero_money, zero_taxed_money
from ..discount import DiscountInfo
from ..tax import TaxCalculationStrategy
from ..tax.calculations.checkout import update_checkout_prices_with_flat_rates
from ..tax.utils import (
    get_charge_taxes_for_checkout,
    get_tax_calculation_strategy_for_checkout,
    normalize_tax_rate_for_db,
)
from .models import Checkout

if TYPE_CHECKING:
    from ..account.models import Address
    from ..plugins.manager import PluginsManager
    from .fetch import CheckoutInfo, CheckoutLineInfo


def checkout_shipping_price(
    *,
    manager: "PluginsManager",
    checkout_info: "CheckoutInfo",
    lines: Iterable["CheckoutLineInfo"],
    address: Optional["Address"],
    discounts: Optional[Iterable[DiscountInfo]] = None,
) -> "TaxedMoney":
    """Return checkout shipping price.

    It takes in account all plugins.
    """
    currency = checkout_info.checkout.currency
    checkout_info, _ = fetch_checkout_prices_if_expired(
        checkout_info,
        manager=manager,
        lines=lines,
        address=address,
        discounts=discounts,
    )
    return quantize_price(checkout_info.checkout.shipping_price, currency)


def checkout_shipping_tax_rate(
    *,
    manager: "PluginsManager",
    checkout_info: "CheckoutInfo",
    lines: Iterable["CheckoutLineInfo"],
    address: Optional["Address"],
    discounts: Optional[Iterable[DiscountInfo]] = None,
) -> Decimal:
    """Return checkout shipping tax rate.

    It takes in account all plugins.
    """
    checkout_info, _ = fetch_checkout_prices_if_expired(
        checkout_info,
        ma