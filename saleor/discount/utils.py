import datetime
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from functools import partial
from typing import (
    TYPE_CHECKING,
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    cast,
)

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from prices import Money, TaxedMoney, fixed_discount, percentage_discount

from ..channel.models import Channel
from ..core.taxes import zero_money
from . import DiscountInfo
from .models import (
    DiscountValueType,
    NotApplicable,
    Sale,
    SaleChannelListing,
    VoucherCustomer,
)

if TYPE_CHECKING:
    from ..account.models import User
    from ..checkout.fetch import CheckoutInfo, CheckoutLineInfo
    from ..order.models import Order
    from ..plugins.manager import PluginsManager
    from ..product.models import Collection, Product
    from .models import Voucher

CatalogueInfo = DefaultDict[str, Set[Union[int, str]]]
CATALOGUE_FIELDS = ["categories", "collections", "products", "variants"]


def increase_voucher_usage(voucher: "Voucher") -> None:
    """Increase voucher uses by 1."""
    voucher.used = F("used") + 1
    voucher.save(update_fields=["used"])


def decrease_voucher_usage(voucher: "Voucher") -> None:
    """Decrease voucher uses by 1."""
    voucher.used = F("used") - 1
    voucher.save(update_fields=["used"])


def add_voucher_usage_by_customer(voucher: "Voucher", customer_email: str) -> None:
    _, created = VoucherCustomer.objects.get_or_create(
        voucher=voucher, customer_email=customer_email
    )
    if not created:
        raise NotApplicable("This offer is only valid once per customer.")


def remove_voucher_usage_by_customer(voucher: "Voucher", customer_email: str) -> None:
    voucher_customer = VoucherCustomer.objects.filter(
        voucher=voucher, customer_email=customer_email
    )
    if voucher_customer:
        voucher_customer.delete()


def release_voucher_usage(voucher: Optional["Voucher"], user_email: Optional[str]):
    if not voucher:
        return
    if voucher.usage_limit:
        decrease_voucher_usage(voucher)
    if user_email:
        remove_voucher_usage_by_customer(voucher, user_email)


def get_product_discount_on_sale(
    product: "Product",
    product_collections: Set[int],
    discount: DiscountInfo,
    channel: "Channel",
    variant_id: Optional[int] = None,
) -> Tuple[int, Callable]:
    """Return sale id, discount value if product is on sale or raise NotApplicable."""
    is_product_on_sale = (
        product.id in discount.product_ids
        or product.category_id in discount.category_ids
        or bool(product_collections.intersection(discount.collection_ids))
    )
    is_variant_on_sale = variant_id and variant_id in discount.variants_ids
    if is_product_on_sale or is_variant_on_sale:
        sale_channel_listing = discount.channel_listings.get(channel.slug)
        return discount.sale.id, discount.sale.get_discount(sale_channel_listing)
    raise NotApplicable("Discount not applicable for this product")


def get_product_discounts(
    *,
    product: "Product",
    collections: Iterable["Collection"],
    discounts: Iterable[DiscountInfo],
    channel: "Channel",
    variant_id: Optional[int] = None,
) -> Iterator[Tuple[int, Callable]]:
    """Return sale ids, discount values for all discounts applicable to a product."""
    product_collections = set(pc.id for pc in collections)
    for discount in discounts:
        try:
            yield get_product_discount_on_sale(
                product, product_collections, discount, channel, variant_id=variant_id
            )
        except NotApplicable:
            pass


def get_sale_id_with_min_price(
    *,
    product: "Product",
    price: Money,
    collections: Iterable["Collection"],
    discounts: Optional[Iterable[DiscountInfo]],
    channel: "Channel",
    variant_id: Optional[int] = None,
) -> Tuple[Optional[int], Money]:
    """Return a sale_id and minimum product's price."""
    available_discounts = [
        (sale_id, discount)
        for sale_id, discount in get_product_discounts(
            product=product,
            collections=collections,
            discounts=discounts or [],
            channel=channel,
            variant_id=varian