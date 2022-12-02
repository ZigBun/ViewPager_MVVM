from typing import Iterable

import graphene
from django.core.exceptions import ValidationError

from ....checkout import AddressType
from ....checkout.checkout_cleaner import (
    clean_checkout_shipping,
    validate_checkout_email,
)
from ....checkout.complete_checkout import complete_checkout
from ....checkout.error_codes import CheckoutErrorCode
from ....checkout.fetch import (
    CheckoutInfo,
    CheckoutLineInfo,
    fetch_checkout_info,
    fetch_checkout_lines,
)
from ....checkout.utils import is_shipping_required
from ....core import analytics
from ....order import models as order_models
from ....permission.enums import AccountPermissions
from ...account.i18n import I18nMixin
from ...app.dataloaders import get_app_promise
from ...core import ResolveInfo
from ...core.descriptions import ADDED_IN_34, ADDED_IN_38, DEPRECATED_IN_3X_INPUT
from ...core.fields import JSONString
from ...core.mutations import BaseMutation
from ...core.scalars import UUID
from ...core.types import CheckoutError, NonNullList
from ...core.validators import validate_one_of_args_is_in_mutation
from ...discount.dataloaders import load_discounts
from ...meta.mutations import MetadataInput
from ...order.types import Order
from ...plugins.dataloaders import get_plugin_manager_promise
from ...site.dataloaders import get_site_promise
from ...utils import get_user_or_app_from_context
from ..types import Checkout
from .utils import get_checkout


class CheckoutComplete(BaseMutation, I18nMixin):
    order = graphene.Field(Order, description="Placed order.")
    confirmation_needed = graphene.Boolean(
        required=True,
        default_value=False,
        description=(
            "Set to true if payment needs to be confirmed"
            " before checkout is complete."
        ),
    )
    confirmation_data = JSONString(
        required=False,
        description=(
            "Confirmation data used to process additional authorization steps."
        ),
    )

    class Arguments:
        id = graphene.ID(
            description="The checkout's ID." + ADDED_IN_34,
            required=False,
        )
        token = UUID(
            description=f"Checkout token.{DEPRECATED_IN_3X_INPUT} Use `id` instead.",
            required=False,
        )
        checkout_id = graphene.ID(
            required=False,
            description=(
                f"The ID of the checkout. {DEPRECATED_IN_3X_INPUT} Use `id` instead."
            ),
        )
        store_source = graphene.Boolean(
            default_value=False,
            description=(
                "Determines whether to store the payment source for future usage. "
                f"{DEPRECATED_IN_3X_INPUT} Use checkoutPaymentCreate for this action."
            ),
        )
        redirect_url = grap