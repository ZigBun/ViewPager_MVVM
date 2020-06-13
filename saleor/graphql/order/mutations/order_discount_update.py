import copy

import graphene
from django.core.exceptions import ValidationError

from ....core.tracing import traced_atomic_transaction
from ....order import events, models
from ....order.calculations import fetch_order_prices_if_expired
from ....order.error_codes import OrderErrorCode
from ....permission.enums import OrderPermissions
from ...app.dataloaders import get_app_promise
from ...core import ResolveInfo
from ...core.types import OrderError
from ...discount.types import OrderDiscount
from ...plugins.dataloaders import get_plugin_manager_promise
from ..types import Order
from .order_discount_common import OrderDiscountCommon, OrderDiscountCommonInput


class OrderDiscountUpdate(OrderDiscountCommon):
    order = graphene.Field(Order, description="Order which has been discounted.")

    class Arguments:
        discount_id = graphene.ID(
            description="ID of a discount to update.", required=True
        )
        input = OrderDiscountCommonInput(
            required=True,
            description="Fields required to update a discount for the order.",
        )

    class Meta:
        description = "Update discount for the order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def validate(cls, info: ResolveInfo, order: models.Order, order_discount, input):
        cls.validate_order(info, order)
        input["value"] = input.get("value") or order_discount.value
        input["value_type"] = input.get("value_type") or order_discount.value_type

        cls.validate_order_discount_input(info, order.undiscounted_total.gross, input)

    @classmethod
    def perform_mutation(  # type: ignore[override]
        cls, _root, info: ResolveInfo, /, *, disc