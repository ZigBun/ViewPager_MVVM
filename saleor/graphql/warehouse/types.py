import graphene
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ...permission.enums import OrderPermissions, ProductPermissions
from ...warehouse import models
from ...warehouse.reservations import is_reservation_enabled
from ..account.dataloaders import AddressByIdLoader
from ..channel import ChannelContext
from ..core import ResolveInfo
from ..core.connection import CountableConnection, create_connection_slice
from ..core.descriptions import (
    ADDED_IN_31,
    ADDED_IN_310,
    DEPRECATED_IN_3X_FIELD,
    DEPRECATED_IN_3X_INPUT,
    PREVIEW_FEATURE,
)
from ..core.fields import ConnectionField, PermissionsField
from ..core.types import ModelObjectType, NonNullList
from ..meta.types import ObjectWithMetadata
from ..product.dataloaders import ProductVariantByIdLoader
from ..site.dataloaders import load_site_callback
from .dataloaders import WarehouseByIdLoader
from .enums import WarehouseClickAndCollectOptionEnum


class WarehouseInput(graphene.InputObjectType):
    slug = graphene.String(description="Warehouse slug.")
    email = graphene.String(description="The email address of the warehouse.")
    external_reference = graphene.String(
        description="External ID of the warehouse." + ADDED_IN_310, required=False
    )


class WarehouseCreateInput(WarehouseInput):
    name = graphene.String(description="Warehouse name.", required=True)
    address = graphene.Field(
        "saleor.graphql.account.types.AddressInput",
        description="Address of the warehouse.",
        required=True,
    )
    shipping_zones = NonNullList(
        graphene.ID,
        description="Shipping zones supported by the warehouse."
        + DEPRECATED_IN_3X_INPUT
        + " Providing the zone ids will raise a ValidationError.",
    )


class WarehouseUpdateInput(WarehouseInput):
    name = graphene.String(description="Warehouse name.", required=False)
    address = graphene.Field(
        "saleor.graphql.account.types.AddressInput",
        description="Address of the warehouse.",
        required=False,
    )
    click_and_collect_option = WarehouseClickAndCollectOptionEnum(
        description=(
            "Click and collect options: local, all or disabled."
            + ADDED_IN_31
            + PREVIEW_FEATURE
        ),
        required=False,
    )
    is_private = graphene.Boolean(
        description="Visibility of warehouse stocks." + ADDED_IN_31 + PREVIEW_FEATURE,
        required=False,
    )


class Warehouse(ModelObjectType[models.Warehouse]):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)
    slug = graphene.String(required=True)
    email = graphene.String(required=True)
    is_private = graphene.Boolean(required=True)
    address = graphene.Field("saleor.graphql.account.types.Address", required=True)
    company_name = graphene.String(
        required=True,
        description="Warehouse company name.",
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Use `Address.companyName` instead."
        ),
    )
    click_and_collect_option = WarehouseClickAndCollectOptionEnum(
        description=(
            "Click and collect options: local, all or disabled."
            + ADDED_IN_31
            + PREVIEW_FEATURE
        ),
        required=True,
    )
    shipping_zones = ConnectionField(
        "saleor.graphql.shipping.types.ShippingZoneCountableConnection",
        required=True,
    )
    external_reference = graphene.String(
        description=f"External ID of this warehouse. {ADDED_IN_310}", required=False
    )

    class Meta:
        description = "Represents warehouse."
        model = models.Warehouse
        interfaces = [graphene.relay.Node, ObjectWithMetadata]

    @staticmethod
    def resolve_shipping_zones(root, info: ResolveInfo, *_args, **kwargs):
        from ..shipping.types import ShippingZoneCountableConnection

        instances = root.shipping_zones.all()
        slice = create_connection_slice(
            instances, info, kwargs, ShippingZoneCountableConnection
        )

        edges_with_context = []
        for edge in slice.edges:
            node = edge.node
            edge.node = ChannelContext(node=node, channel_