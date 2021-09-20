from collections import defaultdict
from typing import Dict, List

import graphene
from django.core.exceptions import ValidationError

from ....core.tracing import traced_atomic_transaction
from ....discount import DiscountValueType, models
from ....discount.error_codes import DiscountErrorCode
from ....permission.enums import DiscountPermissions
from ...channel import ChannelContext
from ...channel.mutations import BaseChannelListingMutation
from ...core import ResolveInfo
from ...core.scalars import PositiveDecimal
from ...core.types import DiscountError, NonNullList
from ...core.validators import validate_price_precision
from ...plugins.dataloaders import get_plugin_manager_promise
from ..types import Voucher


class VoucherChannelListingAddInput(graphene.InputObjectType):
    channel_id = graphene.ID(required=True, description="ID of a channel.")
    discount_value = PositiveDecimal(description="Value of the voucher.")
    min_amount_spent = PositiveDecimal(
        description="Min purchase amount required to apply the voucher."
    )


class VoucherChannelListingInput(graphene.InputObjectType):
    add_channels = NonNullList(
        VoucherChannelListingAddInput,
        description="List of channels to which the voucher should be assigned.",
        required=False,
    )
    remove_channels = NonNullList(
        graphene.ID,
        description="List of channels from which the voucher should be unassigned.",
        required=False,
    )


class VoucherChannelListingUpdate(BaseChannelListingMutation):
    voucher = graphene.Field(Voucher, description="An updated voucher instance.")

    class Arguments:
        id = graphene.ID(required=True, description="ID of a voucher to update.")
        input = VoucherChannelListingInput(
            required=True,
            description="Fields required to update voucher channel listings.",
        )

    class Meta:
        description = "Manage voucher's availability in channels."
        permissions = (DiscountPermissions.MANAGE_DISCOUNTS,)
        error_type_class = DiscountError
        error_type_field = "discount_errors"

    @classmethod
    def clean_discount_values_per_channel(cls, cleaned_input, voucher, error_dict):
        channel_slugs_assigned_to_voucher = voucher.channel_listings.values_list(
            "channel__slug", flat=True
        )

        for cleaned_channel in cleaned_input.get("add_channels", []):
            channel = cleaned_channel.get("channel", None)
            if not channel:
                continue
            discount_value = cleaned_channel.get("discount_value", "")
            # New channel listing requires discout value. It raises validation error for
            # `discout_value` == `None`.
            # Updating channel listing doesn't require to pass `discout_value`.
            should_create = channel.slug not in channel_slugs_assigned_to_voucher
            missing_required_value = not discount_value and should_create
            if missing_required_value or discount_value is None:
                error_dict["channels_without_value"].append(
                    cleaned_channel["channel_id"]
                )
            # Validate value precision if it is fixed amount voucher
            if voucher.discount_value_type == DiscountValueType.FIXED:
                try:
                    validate_price_precision(discount_value, channel.currency_code)
                except ValidationError:
                    error_dict["channels_with_invalid_value_precision"].append(
                        cleaned_channel["channel_id"]
                    )
            elif voucher.discount_value_type == DiscountValueType.PERCENTAGE:
                if discount_value > 100:
                    error_dict["channels_with_invalid_percentage_value"].append(
                        cleaned_channel["channel_id"]
                    )

            min_amount_spent = cleaned_channel.get("min_amount_spent", None)
            if min_amount_spent:
                try:
                    validate_price_precision(min_amount_spent, channel.currency_code)
                except ValidationError:
                    error_dict[
                        "channels_with_invalid_min_amount_spent_precision"
                    ].append(cleaned_channel["channel_id"])

    @classmethod
    def clean_discount_values(
        cls, cleaned_input, voucher, errors: defaultdict[str, List[ValidationError]]
    ):
        error_dict: Dict[str, List[ValidationError]] = {
            "channels_without_value": [],
            "channels_with_invalid_value_precision": [],
            "channels_with_invalid_percentage_value": [],
            "channels_with_invalid_min_amount_spent_precision": [],
        }
        cls.clean_discount_values_per_channel(
            cleaned_input,
            voucher,
            error_dict,
        )
        channels_without_value = error_dict["channels_without_value"]
        if channels_without_value:
            errors["discount_value"].append(
                ValidationError(
                    "Value is required for voucher.",
                    code=DiscountErrorCode.REQUIRED.value,
                    params={"channels"