import datetime
import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Any,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Optional,
    Type,
    Union,
    cast,
)

import graphene
import pytz
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q, QuerySet

from ....checkout import models
from ....checkout.error_codes import CheckoutErrorCode
from ....checkout.fetch import CheckoutInfo, CheckoutLineInfo
from ....checkout.utils import (
    calculate_checkout_quantity,
    clear_delivery_method,
    is_shipping_required,
)
from ....core.exceptions import InsufficientStock, PermissionDenied
from ....permission.enums import CheckoutPermissions
from ....product import models as product_models
from ....product.models import ProductChannelListing, ProductVariant
from ....shipping import interface as shipping_interface
from ....warehouse import models as warehouse_models
from ....warehouse.availability import check_stock_and_preorder_quantity_bulk
from ...core import ResolveInfo
from ...core.validators import validate_one_of_args_is_in_mutation
from ..types import Checkout

if TYPE_CHECKING:
    from ...core.mutations import BaseMutation


ERROR_DOES_NOT_SHIP = "This checkout doesn't need shipping"


@dataclass
class CheckoutLineData:
    variant_id: Optional[str] = None
    line_id: Optional[str] = None
    quantity: int = 0
    quantity_to_update: bool = False
    custom_price: Optional[Decimal] = None
    custom_price_to_update: bool = False
    metadata_list: Optional[list] = None


def clean_delivery_method(
    checkout_info: "CheckoutInfo",
    lines: Iterable[CheckoutLineInfo],
    method: Optional[
        Union[
            shipping_interface.ShippingMethodData,
            warehouse_models.Warehouse,
        ]
    ],
) -> bool:
    """Check if current shipping method is valid."""
    if not method:
        # no shipping method was provided, it is valid
        return True

    if not is_shipping_required(lines):
        raise ValidationError(
            ERROR_DOES_NOT_SHIP, code=CheckoutErrorCode.SHIPPING_NOT_REQUIRED.value
        )

    if not checkout_info.shipping_address and isinstance(
        method, shipping_interface.ShippingMethodData
    ):
        raise ValidationError(
            "Cannot choose a shipping method for a checkout without the "
            "shipping address.",
            code=CheckoutErrorCode.SHIPPING_ADDRESS_NOT_SET.value,
        )

    valid_methods = checkout_info.valid_delivery_methods
    return method in valid_methods


def update_checkout_shipping_method_if_invalid(
    checkout_info: "CheckoutInfo", lines: Iterable[CheckoutLineInfo]
):
    quantity = calculate_checkout_quantity(lines)

    # remove shipping method when empty checkout
    if quantity == 0 or not is_shipping_required(lines):
        clear_delivery_method(checkout_info)

    is_valid = clean_delivery_method(
        checkout_info=checkout_info,
        lines=lines,
        method=checkout_info.delivery_method_info.delivery_method,
    )

    if not is_valid:
        clear_delivery_method(checkout_info)


def get_variants_and_total_quantities(
    variants: List[ProductVariant],
    lines_data: Iterable[CheckoutLineData],
    quantity_to_update_check=False,
):
    variants_total_quantity_map: DefaultDict[ProductVariant, int] = defaultdict(int)
    mapped_data: DefaultDict[Optional[str], int] = defaultdict(int)

    if quantity_to_update_check:
        lines_data = filter(lambda d: d.quantity_to_upda