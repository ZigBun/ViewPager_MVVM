from collections import defaultdict
from typing import Dict, List, cast

import graphene
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from django.db.utils import IntegrityError

from ....channel import models as channel_models
from ....core.tracing import traced_atomic_transaction
from ....permission.enums import ShippingPermissions
from ....product import models as product_models
from ....shipping import models
from ....shipping.error_codes import ShippingErrorCode
from ....shipping.tasks import (
    drop_invalid_shipping_methods_relations_for_given_channels,
)
from ....shipping.utils import (
    default_shipping_zone_exists,
    get_countries_without_shipping_zone,
)
from ...channel.types import ChannelContext
from ...core import ResolveInfo
from ...core.fields import JSONString
from ...core.mutations import BaseMutation, ModelDeleteMutation, ModelMutation
from ...core.scalars import WeightScalar
from ...core.types import NonNullList, ShippingError
from ...plugins.dataloaders import get_plugin_manager_promise
from ...product import types as product_types
from ...shipping import types as shipping_types
from ...utils import resolve_global_ids_to_primary_keys
from ...utils.validators import check_for_duplicates
from ..enums import PostalCodeRuleInclusionTypeEnum, ShippingMethodTypeEnum
from ..types import ShippingMethodPostalCodeRule, ShippingMethodType, ShippingZone


class ShippingPostalCodeRulesCreateInputRange(graphene.InputObjectType):
    start = graphene.String(
        required=True, description="Start range of the postal code."
    )
    end = graphene.String(required=False, description="End range of the postal code.")


class ShippingPriceInput(graphene.InputObjectType):
    name = graphene.String(description="Name of the shipping method.")
    description = JSONString(description="Shipping method description.")
    minimum_order_weight = WeightScalar(
        description="Minimum order weight to use this shipping method."
    )
    maximum_order_weight = WeightScalar(
        description="Maximum order weight to use this shipping method."
    )
    maximum_delivery_days = graphene.Int(
        description="Maximum number of days for delivery."
    )
    minimum_delivery_days = graphene.Int(
        description="Minimal number of days for delivery."
    )
    type = ShippingMethodTypeEnum(description="Shipping type: price or weight based.")
    shipping_zone = graphene.ID(
        description="Shipping zone this method belongs to.", name="shippingZone"
    )
    add_postal_code_rules = NonNullList(
        ShippingPostalCodeRulesCreateInputRange,
        description="Postal code rules to add.",
    )
    delete_postal_code_rules = NonNullList(
        graphene.ID,
        description="Postal code rules to delete.",
    )
    inclusion_type = PostalCodeRuleInclusionTypeEnum(
        description="Inclusion type for currently assigned postal code rules.",
    )
    tax_class = graphene.ID(
        description=(
            "ID of a tax class to assign to this shipping method. If not provided, "
            "the default tax class will be used."
        ),
        required=False,
    )


class ShippingZoneCreateInput(graphene.InputObjectType):
    name = graphene.String(
        description="Shipping zone's name. Visible only to the staff."
    )
    description = graphene.String(description="Description of the shipping zone.")
    countries = NonNullList(
        graphene.String, description="List of countries in this shipping zone."
    )
    default = graphene.Boolean(
        description=(
            "Default shipping zone will be used for countries not covered by other "
            "zones."
        )
    )
    add_warehouses = NonNullList(
        graphene.ID,
        description="List of warehouses to assign to a shipping zone",
    )
    add_channels = NonNullList(
        graphene.ID,
        description="List of channels to assign to the shipping zone.",
    )


class ShippingZoneUpdateInput(ShippingZoneCreateInput):
    remove_warehouses = NonNullList(
        graphene.ID,
        description="List of warehouses to unassign from a shipping zone",
    )
    remove_channels = NonNullList(
        graphene.ID,
        description="List of channels to unassign from the shipping zone.",
    )


class ShippingZoneMixin:
    @classmethod
    def clean_input(cls, info: ResolveInfo, instance, data, **kwargs):
        errors: defaultdict[str, List[ValidationError]] = defaultdict(list)
        cls.check_duplicates(
            errors, data, "add_warehouses", "remove_warehouses", "warehouses"
        )
        cls.check_duplicates(
            errors, data, "add_channels", "remove_channels", "channels"
        )

        if errors:
            raise ValidationError(errors)

        cleaned_input = super().clean_input(  # type: ignore[misc] # mixin
            info, instance, data, **kwargs
        )
        if add_warehouses := cleaned_input.get("add_warehouses"):
            cls.clean_add_warehouses(instance, add_warehouses, cleaned_input)
        cleaned_input = cls.clean_default(instance, cleaned_input)
        return cleaned_input

    @classmethod
    def check_duplicates(
        cls,
        errors: dict,
        input_data: dict,
        add_field: str,
        remove_field: str,
        error_class_field: str,
    ):
        """Check if any items are on both input field.

        Raise error if some of items are duplicated.
        """
        error = check_for_duplicates(
            input_data, add_field, remove_field, error_class_field
        )
        if error:
            error.code = ShippingErrorCode.DUPLICATED_INPUT_ITEM.value
            errors[error_class_field].append(error)

    @classmethod
    def clean_add_warehouses(cls, shipping_zone, warehouses, cleaned_input):
        """Check if all warehouses to add has common channel with shipping zone.

        Raise and error when the condition is not fulfilled.
        """
        warehouse_ids = [warehouse.id for warehouse in warehouses]

        remove_channel_ids = set()
        if remove_channels := cleaned_input.get("remove_channels"):
            remove_channel_ids = {channel.id for channel in remove_channels}

        add_channel_ids = set()
        if add_channels := cleaned_input.get("add_channels"):
            add_channel_ids = {channel.id for channel in add_channels}

     