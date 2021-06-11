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

        ChannelWarehouse = channel_models.Channel.warehouses.through  # type: ignore[attr-defined] # raw access to the through model # noqa: E501
        channel_warehouses = ChannelWarehouse.objects.filter(
            warehouse_id__in=warehouse_ids
        )

        # any warehouse from the list cannot be assigned when:
        # 1) where there are no channels assigned to any warehouse
        # 2) any channel is will be not assigned to the shipping zone
        if not channel_warehouses or (not shipping_zone.id and not add_channel_ids):
            invalid_warehouse_ids = warehouse_ids

        warehouse_to_channel_mapping = defaultdict(set)
        for warehouse_id, channel_id in channel_warehouses.values_list(
            "warehouse_id", "channel_id"
        ):
            warehouse_to_channel_mapping[warehouse_id].add(channel_id)

        # if the shipping zone does not exist yet, all zone channels will be channels
        # provided in `add_channels` field
        shipping_zone_channel_ids = (
            add_channel_ids
            if not shipping_zone.id
            else cls._get_shipping_zone_channel_ids(
                shipping_zone, remove_channel_ids, add_channel_ids
            )
        )

        invalid_warehouse_ids = cls._find_invalid_warehouses(
            warehouse_to_channel_mapping, warehouse_ids, shipping_zone_channel_ids
        )

        if invalid_warehouse_ids:
            invalid_warehouses = {
                graphene.Node.to_global_id("Warehouse", pk)
                for pk in invalid_warehouse_ids
            }
            raise ValidationError(
                {
                    "add_warehouses": ValidationError(
                        "Only warehouses that have common channel with shipping zone "
                        "can be assigned.",
                        code=ShippingErrorCode.INVALID.value,
                        params={
                            "warehouses": invalid_warehouses,
                        },
                    )
                }
            )

    @staticmethod
    def _get_shipping_zone_channel_ids(
        shipping_zone, remove_channel_ids, add_channel_ids
    ):
        # get shipping zone channels
        ShippingZoneChannel = models.ShippingZone.channels.through
        shipping_zone_channel_ids = set(
            ShippingZoneChannel.objects.filter(shippingzone_id=shipping_zone.id)
            .exclude(channel_id__in=remove_channel_ids)
            .values_list("channel_id", flat=True)
        )
        # shipping zone channels set need to be updated with channels
        # that will be removed and added to shipping zone
        return shipping_zone_channel_ids | add_channel_ids

    @staticmethod
    def _find_invalid_warehouses(
        warehouse_to_channel_mapping, warehouse_ids, zone_channel_ids
    ):
        invalid_warehouse_ids = []
        for warehouse_id in warehouse_ids:
            warehouse_channels = warehouse_to_channel_mapping.get(warehouse_id)
            # warehouse cannot be added if it hasn't got any channel assigned
            # or if it does not have common channel with shipping zone
            if not warehouse_channels or not warehouse_channels.intersection(
                zone_channel_ids
            ):
                invalid_warehouse_ids.append(warehouse_id)
        return invalid_warehouse_ids

    @classmethod
    def clean_default(cls, instance, data):
        default = data.get("default")
        if default:
            if default_shipping_zone_exists(instance.pk):
                raise ValidationError(
                    {
                        "default": ValidationError(
                            "Default shipping zone already exists.",
                            code=ShippingErrorCode.ALREADY_EXISTS.value,
                        )
                    }
                )
            else:
                countries = get_countries_without_shipping_zone()
                data["countries"].extend([country for country in countries])
        else:
            data["default"] = False
        return data

    @classmethod
    def _save_m2m(cls, info: ResolveInfo, instance, cleaned_data):
        with traced_atomic_transaction():
            super()._save_m2m(info, instance, cleaned_data)  # type: ignore[misc] # mixin # noqa: E501

            add_warehouses = cleaned_data.get("add_warehouses")
            if add_warehouses:
                instance.warehouses.add(*add_warehouses)

            remove_warehouses = cleaned_data.get("remove_warehouses")
            if remove_warehouses:
                instance.warehouses.remove(*remove_warehouses)

            add_channels = cleaned_data.get("add_channels")
            if add_channels:
                instance.channels.add(*add_channels)

            remove_channels = cleaned_data.get("remove_channels")
            if remove_channels:
                instance.channels.remove(*remove_channels)
                shipping_channel_listings = (
                    models.ShippingMethodChannelListing.objects.filter(
                        shipping_method__shipping_zone=instance,
                        channel__in=remove_channels,
                    )
                )
                shipping_method_ids = list(
                    shipping_channel_listings.values_list(
                        "shipping_method_id", flat=True
                    )
                )
                shipping_channel_listings.delete()
                channel_ids = [channel.id for channel in remove_channels]
                cls.delete_invalid_shipping_zone_to_warehouse_relation(instance)
                drop_invalid_shipping_methods_relations_for_given_channels.delay(
                    shipping_method_ids, channel_ids
                )

    @classmethod
    def delete_invalid_shipping_zone_to_warehouse_relation(cls, shipping_zone):
        """Drop zone-warehouse relations that becomes invalid after channels deletion.

        Remove all shipping zone to warehouse relations that will not have common
        channel after removing given channels from the shipping zone.
        """
        WarehouseShippingZone = models.ShippingZone.warehouses.through  # type: ignore[attr-defined] # raw access to the through model # noqa: E501
        ChannelWarehouse = channel_models.Channel.warehouses.through  # type: ignore[attr-defined] # raw access to the through model # noqa: E501
        ShippingZoneChannel = models.ShippingZone.channels.through

        warehouse_shipping_zones = WarehouseShippingZone.objects.filter(
            shippingzone_id=shipping_zone.id
        )

        channel_warehouses = ChannelWarehouse.objects.filter(
            Exists(
                warehouse_shipping_zones.filter(warehouse_id=OuterRef("warehouse_id"))
            )
        )

        warehouse_to_channel_mapping = defaultdict(set)
        for warehouse_id, channel_id in channel_warehouses.values_list(
            "warehouse_id", "channel_id"
        ):
            warehouse_to_channel_mapping[warehouse_id].add(channel_id)

        shipping_zone_channel_ids = set(
            ShippingZoneChannel.objects.filter(
                shippingzone_id=shipping_zone.id
            ).values_list("channel_id", flat=True)
        )

        shipping_zone_warehouses_to_delete = []
        for id, warehouse_id in warehouse_shipping_zones.values_list(
            "id", "warehouse_id"
        ):
            warehouse_channels = warehouse_to_channel_mapping.get(warehouse_id, set())
            # if there is no common