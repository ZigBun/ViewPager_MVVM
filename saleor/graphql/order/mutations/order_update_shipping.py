import graphene
from django.core.exceptions import ValidationError

from ....core.taxes import zero_money, zero_taxed_money
from ....order import models
from ....order.error_codes import OrderErrorCode
from ....order.utils import invalidate_order_prices
from ....permission.enums import OrderPermissions
from ....shipping import models as shipping_models
from ....shipping.utils import convert_to_shipping_method_data
from ...core import ResolveInfo
from ...core.mutations import BaseMutation
from ...core.types import OrderError
from ...plugins.dataloaders import get_plugin_manager_promise
from ...shipping.types import ShippingMethod
from ..types import Order
from .utils import EditableOrderValidationMixin, clean_order_update_shipping


class OrderUpdateShippingInput(graphene.InputObjectType):
    shipping_method = graphene.ID(
        description="ID of the selected shipping method,"
        " pass null to remove currently assigned shipping method.",
        name="shippingMethod",
    )


class OrderUpdateShipping(EditableOrderValidationMixin, Ba