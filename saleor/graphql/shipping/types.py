from typing import Union

import graphene
from django.db.models import QuerySet
from graphene import relay

from ...core.weight import convert_weight_to_default_weight_unit
from ...permission.enums import CheckoutPermissions, ShippingPermissions
from ...product import models as product_models
from ...shipping import models
from ...shipping.interface import ShippingMethodData
from ..account.enums import CountryCodeEnum
from ..channel import ChannelQsContext
from ..channel.dataloaders import ChannelByIdLoader
from ..channel.types import (
    Channel,
    ChannelContext,
    ChannelContextType,
    ChannelContextTypeWithMetadata,
    ChannelContextTypeWithMetadataForObjectType,
)
from ..core.connection import CountableConnection, create_connection_slice
from ..core.descriptions import (
    ADDED_IN_36,
    DEPRECATED_IN_3X_FIELD,
    PREVIEW_FEATURE,
    RICH_CONTENT,
)
from ..core.fields import ConnectionField, JSONString, PermissionsField
from ..core.tracing import traced_resolver
from ..core.types import (
    CountryDisplay,
    ModelObjectType,
    Money,
    MoneyRange,
    NonNullList,
    Weight,
)
from ..meta.types import ObjectWithMetadata
from ..shipping.resolvers import resolve_price_range, resolve_shipping_translation
from ..tax.dataloaders import TaxClassByIdLoader
from ..tax.types import TaxClass
from ..translations.fields import TranslationField
from ..translations.types import ShippingMethodTranslation
from ..warehouse.types import Warehouse
from .dataloaders import (
    ChannelsByShippingZoneIdLoader,
    PostalCodeRulesByShippingMethodIdLoader,
    ShippingMethodChannelListingByShippingMethodIdAndChannelSlugLoader,
    ShippingMethodChannelListingByShippingMethodIdLoader,
    ShippingMethodsByShippingZoneIdAndChannelSlugLoader,
    ShippingMethodsByShippingZoneIdLoader,
)
from .enums import PostalCodeRuleInclusionTypeEnum, ShippingMethodTypeEnum


class ShippingMethodChannelListing(
    ModelObjectType[models.ShippingMethodChannelListing]
):
    id = graphene.GlobalID(required=True)
    channel = graphene.Field(Channel, required=True)
    maximum_order_price = graphene.Field(Money)
    minimum_order_price = graphene.Field(Money)
    price = graphene.Field(Money)

    class Meta:
        description = "Represents shipping method channel listing."
        model = models.ShippingMethodChannelListing
        interfaces = [relay.Node]

    @staticmethod
    def resolve_channel(root: models.ShippingMethodChannelListing, info):
        return ChannelByIdLoader(info.context).load(root.channel_id)

    @staticmethod
    def resolve_minimum_order_price(root: models.ShippingMethodChannelListing, info):
        if root.minimum_order_price_amount is None:
            return None
        else:
            return root.minimum_order_price


class ShippingMethodPostalCodeRule(
    ModelObjectType[models.ShippingMethodPostalCodeRule]
):
    start = graphene.String(description="Start address range.")
    end = graphene.String(description="End address range.")
    inclusion_type = PostalCodeRuleInclusionTypeEnum(
        description="Inclusion type of the postal code rule."
    )

    class Meta:
        description = "Represents shipping method postal code rule."
        interfaces = [relay.Node]
        model = models.ShippingMethodPostalCodeRule


class ShippingMethodType(ChannelContextTypeWithMetadataForObjectType):
    """Represents internal shipping method managed within Saleor.

    Internal and external (fetched by sync webhooks) shipping methods are later
    represented by `ShippingMethod` objects as part of orders and checkouts.
    """

    id = graphene.ID(required=True, description="Shipping method ID.")
    name = graphene.String(required=True, description="Shipping method name.")
    description = JSONString(description="Shipping method description." + RICH_CONTENT)
    type = ShippingMethodTypeEnum(description="Type of the shipping method.")
    translation = TranslationField(
        ShippingMethodTranslation,
        type_name="shipping method",
        resolver=None,  # Disable defa