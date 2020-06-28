import graphene
from promise import Promise

from ...checkout import calculations, models
from ...checkout.base_calculations import (
    calculate_undiscounted_base_line_total_price,
    calculate_undiscounted_base_line_unit_price,
)
from ...checkout.utils import get_valid_collection_points_for_checkout
from ...core.taxes import zero_taxed_money
from ...permission.enums import (
    AccountPermissions,
    CheckoutPermissions,
    PaymentPermissions,
)
from ...shipping.interface import ShippingMethodData
from ...tax.utils import get_display_gross_prices
from ...warehouse import models as warehouse_models
from ...warehouse.reservations import is_reservation_enabled
from ..account.dataloaders import AddressByIdLoader
from ..account.utils import check_is_owner_or_has_one_of_perms
from ..channel import ChannelContext
from ..channel.dataloaders import ChannelByCheckoutLineIDLoader
from ..channel.types import Channel
from ..core import ResolveInfo
from ..core.connection import CountableConnection
from ..core.descriptions import (
    ADDED_IN_31,
    ADDED_IN_34,
    ADDED_IN_35,
    ADDED_IN_38,
    ADDED_IN_39,
    DEPRECATED_IN_3X_FIELD,
    PREVIEW_FEATURE,
)
from ..core.enums import LanguageCodeEnum
from ..core.scalars import UUID
from ..core.tracing import traced_resolver
from ..core.types import ModelObjectType, Money, NonNullList, TaxedMoney
from ..core.utils import str_to_enum
from ..decorators import one_of_permissions_required
from ..discount.dataloaders import DiscountsByDateTimeLoader
from ..giftcard.types import GiftCard
from ..meta import resolvers as MetaResolvers
from ..meta.types import ObjectWithMetadata, _filter_metadata
from ..payment.types import TransactionItem
from ..plugins.dataloaders import (
    get_plugin_manager_promise,
    plugin_manager_promise_callback,
)
from ..product.dataloaders import (
    ProductTypeByProductIdLoader,
    ProductTypeByVariantIdLoader,
    ProductVariantByIdLoader,
)
from ..shipping.types import ShippingMethod
from ..site.dataloaders import load_site_callback
from ..tax.dataloaders import (
    TaxConfigurationByChannelId,
    TaxConfigurationPerCountryByTaxConfigurationIDLoader,
)
from ..utils import get_user_or_app_from_context
from ..warehouse.dataloaders import StocksReservationsByCheckoutTokenLoader
from ..warehouse.types import Warehouse
from .dataloaders import (
    CheckoutByTokenLoader,
    CheckoutInfoByCheckoutTokenLoader,
    CheckoutLinesByCheckoutTokenLoader,
    CheckoutLinesInfoByCheckoutTokenLoader,
    CheckoutMetadataByCheckoutIdLoader,
    TransactionItemsByCheckoutIDLoader,
)
from .utils import prevent_sync_event_circular_query


class GatewayConfigLine(graphene.ObjectType):
    field = graphene.String(required=True, description="Gateway config key.")
    value = graphene.String(description="Gateway config value for key.")

    class Meta:
        description = "Payment gateway client configuration key and value pair."


class PaymentGateway(graphene.ObjectType):
    name = graphene.String(required=True, description="Payment gateway name.")
    id = graphene.ID(required=True, description="Payment gateway ID.")
    config = NonNullList(
        GatewayConfigLine,
        required=True,
        description="Payment gateway client configuration.",
    )
    currencies = NonNullList(
        graphene.String,
        required=True,
        description="Payment gateway supported currencies.",
    )

    class Meta:
        description = (
            "Available payment gateway backend with configuration "
            "necessary to setup client."
        )


class CheckoutLine(ModelObjectType[models.CheckoutLine]):
    id = graphene.GlobalID(required=True)
    variant = graphene.Field(
        "saleor.graphql.product.types.ProductVariant", required=True
    )
    quantity = graphene.Int(required=True)
    unit_price = graphene.Field(
        TaxedMoney,
        description="The unit price of the checkout line, with taxes and discounts.",
        required=True,
    )
    undiscounted_unit_price = graphene.Field(
        Money,
        description="The unit price of the checkout line, without discounts.",
        required=True,
    )
    total_price = graphene.Field(
        TaxedMoney,
        description="The