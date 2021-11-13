import itertools
from dataclasses import dataclass
from functools import singledispatch
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Union,
)
from uuid import UUID

from django.utils.functional import SimpleLazyObject

from ..discount import DiscountInfo, VoucherType
from ..discount.interface import fetch_voucher_info
from ..discount.utils import fetch_active_discounts
from ..shipping.interface import ShippingMethodData
from ..shipping.models import ShippingMethod, ShippingMethodChannelListing
from ..shipping.utils import (
    convert_to_shipping_method_data,
    initialize_shipping_method_active_status,
)
from ..warehouse import WarehouseClickAndCollectOption
from ..warehouse.models import Warehouse

if TYPE_CHECKING:
    from ..account.models import Address, User
    from ..channel.models import Channel
    from ..discount.interface import VoucherInfo
    from ..discount.models import Voucher
    from ..plugins.manager import PluginsManager
    from ..product.models import (
        Collection,
        Product,
        ProductChannelListing,
        ProductType,
        ProductVariant,
        ProductVariantChannelListing,
    )
    from ..tax.models import TaxClass, TaxConfiguration
    from .models import Checkout, CheckoutLine


@dataclass
class CheckoutLineInfo:
    line: "CheckoutLine"
    variant: "ProductVariant"
    channel_listing: "ProductVariantChannelListing"
    product: "Product"
    product_type: "ProductType"
    collections: List["Collection"]
    tax_class: Optional["TaxClass"] = None
    voucher: Optional["Voucher"] = None


@dataclass
class CheckoutInfo:
    checkout: "Checkout"
    user: Optional["User"]
    channel: "Channel"
    billing_address: Optional["Address"]
    shipping_address: Optional["Address"]
    delivery_method_info: "DeliveryMethodBase"
    all_shipping_methods: List["ShippingMethodData"]
    tax_configuration: "TaxConfiguration"
    valid_pick_up_points: List["Warehouse"]
    voucher: Optional["Voucher"] = None

    @property
    def valid_shipping_methods(self) -> List["ShippingMethodData"]:
        return [method for method in self.all_shipping_methods if method.active]

    @property
    def valid_delivery_methods(
        self,
    ) -> List[Union["ShippingMethodData", "Warehouse"]]:
        return list(
            itertools.chain(
                self.valid_shipping_methods,
                self.valid_pick_up_points,
            )
        )

    def get_country(self) -> str:
        address = self.shipping_address or self.billing_address
        if address is None or not address.country:
            return self.checkout.country.code
        return address.country.code

    def get_customer_email(self) -> Optional[str]:
        return self.user.email if self.user else self.checkout.email


@dataclass(frozen=True)
class DeliveryMethodBase:
    delivery_method: Optional[Union["ShippingMethodData", "Warehouse"]] = None
    shipping_address: Optional["Address"] = None
    store_as_customer_address: bool = False

    @property
    def warehouse_pk(self) -> Optional[UUID]:
        pass

    @property
    def delivery_method_order_field(self) -> dict:
        return {"shipping_method": self.delivery_method}

    @property
    def is_local_collection_point(self) -> bool:
        return False

    @property
    def delivery_method_name(self) -> Dict[str, Optional[str]]:
        return {"shipping_method_name": None}

    def get_warehouse_filter_lookup(self) -> Dict[str, Any]:
        return {}

    def is_valid_delivery_method(self) -> bool:
        return False

    def is_method_in_valid_methods(self, checkout_info: "CheckoutInfo") -> bool:
        return False


@dataclass(frozen=True)
class ShippingMethodInfo(DeliveryMethodBase):
    delivery_method: "ShippingMethodData"
    shipping_address: Optional["Address"]
    store_as_customer_address: bool = True

    @property
    def delivery_method_name(self) -> Dict[str, Optional[str]]:
        return {"shipping_method_name": str(self.delivery_method.name)}

    @property
    def delivery_method_order_field(self) -> dict:
        if not self.delivery_method.is_external:
            return {"shipping_method_id": int(self.delivery_method.id)}
        return {}

    def is_valid_delivery_method(self) -> bool:
        return bool(self.shipping_address)

    def is_method_in_valid_methods(self, checkout_info: "CheckoutInfo") -> bool:
        valid_delivery_methods = checkout_info.valid_delivery_methods
        return bool(
            valid_delivery_methods and self.delivery_method in valid_delivery_methods
        )


@dataclass(frozen=True)
class CollectionPointInfo(DeliveryMethodBase):
    delivery_method: "Warehouse"
    shipping_address: Optional["Address"]

    @property
    def warehouse_pk(self):
        return self.delivery_method.pk

    @property
    def delivery_method_order_field(self) -> dict:
        return {"collection_point": self.delivery_method}

    @property
    def is_local_collection_point(self):
        return (
            self.delivery_method.click_and_collect_option
            == WarehouseClickAndCollectOption.LOCAL_STOCK
        )

    @property
    def delivery_method_name(self) -> Dict[str, Optional[str]]:
        return {"collection_point_name": str(self.delivery_method)}

    def get_warehouse_filter_lookup(self) -> Dict[str, Any]:
        return (
            {"warehouse_id": self.delivery_method.pk}
            if self.is_local_collection_point
            else {}
        )

    def is_valid_delivery_method(self) -> bool:
        return (
            self.shipping_addres