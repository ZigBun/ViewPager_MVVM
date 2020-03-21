
import logging
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import graphene
import prices
from django.core.exceptions import ValidationError
from graphene import relay
from promise import Promise

from ...account.models import Address
from ...checkout.utils import get_external_shipping_id
from ...core.anonymize import obfuscate_address, obfuscate_email
from ...core.prices import quantize_price
from ...discount import OrderDiscountType
from ...graphql.checkout.types import DeliveryMethod
from ...graphql.utils import get_user_or_app_from_context
from ...graphql.warehouse.dataloaders import StockByIdLoader, WarehouseByIdLoader
from ...order import OrderStatus, calculations, models
from ...order.models import FulfillmentStatus
from ...order.utils import (
    get_order_country,
    get_valid_collection_points_for_order,
    get_valid_shipping_methods_for_order,
)
from ...payment import ChargeStatus
from ...payment.dataloaders import PaymentsByOrderIdLoader
from ...payment.model_helpers import get_last_payment, get_total_authorized
from ...permission.auth_filters import AuthorizationFilters
from ...permission.enums import (
    AccountPermissions,
    AppPermission,
    OrderPermissions,
    PaymentPermissions,
    ProductPermissions,
)
from ...permission.utils import has_one_of_permissions
from ...product import ProductMediaTypes
from ...product.models import ALL_PRODUCTS_PERMISSIONS
from ...shipping.interface import ShippingMethodData
from ...shipping.models import ShippingMethodChannelListing
from ...shipping.utils import convert_to_shipping_method_data
from ...tax.utils import get_display_gross_prices
from ...thumbnail.utils import (
    get_image_or_proxy_url,
    get_thumbnail_format,
    get_thumbnail_size,
)
from ..account.dataloaders import AddressByIdLoader, UserByUserIdLoader
from ..account.types import User
from ..account.utils import (
    check_is_owner_or_has_one_of_perms,
    is_owner_or_has_one_of_perms,
)
from ..app.dataloaders import AppByIdLoader
from ..app.types import App
from ..channel import ChannelContext
from ..channel.dataloaders import ChannelByIdLoader, ChannelByOrderLineIdLoader
from ..channel.types import Channel
from ..checkout.utils import prevent_sync_event_circular_query
from ..core.connection import CountableConnection
from ..core.descriptions import (
    ADDED_IN_31,
    ADDED_IN_34,
    ADDED_IN_35,
    ADDED_IN_38,
    ADDED_IN_39,
    ADDED_IN_310,
    ADDED_IN_311,
    DEPRECATED_IN_3X_FIELD,
    PREVIEW_FEATURE,
)
from ..core.enums import LanguageCodeEnum
from ..core.fields import PermissionsField
from ..core.mutations import validation_error_to_error_type
from ..core.scalars import PositiveDecimal
from ..core.tracing import traced_resolver
from ..core.types import (
    Image,
    ModelObjectType,
    Money,
    NonNullList,
    OrderError,
    TaxedMoney,
    ThumbnailField,
    Weight,
)
from ..core.utils import str_to_enum
from ..decorators import one_of_permissions_required
from ..discount.dataloaders import OrderDiscountsByOrderIDLoader, VoucherByIdLoader
from ..discount.enums import DiscountValueTypeEnum
from ..discount.types import Voucher
from ..giftcard.dataloaders import GiftCardsByOrderIdLoader
from ..giftcard.types import GiftCard
from ..invoice.dataloaders import InvoicesByOrderIdLoader
from ..invoice.types import Invoice
from ..meta.resolvers import check_private_metadata_privilege, resolve_metadata
from ..meta.types import MetadataItem, ObjectWithMetadata
from ..payment.enums import OrderAction, TransactionStatusEnum
from ..payment.types import Payment, PaymentChargeStatusEnum, TransactionItem
from ..plugins.dataloaders import (
    get_plugin_manager_promise,
    plugin_manager_promise_callback,
)
from ..product.dataloaders import (
    MediaByProductVariantIdLoader,
    ProductByVariantIdLoader,
    ProductChannelListingByProductIdAndChannelSlugLoader,
    ProductImageByProductIdLoader,
    ProductVariantByIdLoader,
    ThumbnailByProductMediaIdSizeAndFormatLoader,
)
from ..product.types import DigitalContentUrl, ProductVariant
from ..shipping.dataloaders import (
    ShippingMethodByIdLoader,
    ShippingMethodChannelListingByChannelSlugLoader,
    ShippingMethodChannelListingByShippingMethodIdAndChannelSlugLoader,
)
from ..shipping.types import ShippingMethod
from ..tax.dataloaders import (
    TaxClassByIdLoader,
    TaxConfigurationByChannelId,
    TaxConfigurationPerCountryByTaxConfigurationIDLoader,
)
from ..tax.types import TaxClass
from ..warehouse.types import Allocation, Stock, Warehouse
from .dataloaders import (
    AllocationsByOrderLineIdLoader,
    FulfillmentLinesByFulfillmentIdLoader,
    FulfillmentLinesByIdLoader,
    FulfillmentsByOrderIdLoader,
    OrderByIdLoader,
    OrderByNumberLoader,
    OrderEventsByOrderIdLoader,
    OrderLineByIdLoader,
    OrderLinesByOrderIdLoader,
    TransactionItemsByOrderIDLoader,
)
from .enums import (
    FulfillmentStatusEnum,
    OrderAuthorizeStatusEnum,
    OrderChargeStatusEnum,
    OrderEventsEmailsEnum,
    OrderEventsEnum,
    OrderOriginEnum,
    OrderStatusEnum,
)
from .utils import validate_draft_order

logger = logging.getLogger(__name__)


def get_order_discount_event(discount_obj: dict):
    currency = discount_obj["currency"]

    amount = prices.Money(Decimal(discount_obj["amount_value"]), currency)

    old_amount = None
    old_amount_value = discount_obj.get("old_amount_value")
    if old_amount_value:
        old_amount = prices.Money(Decimal(old_amount_value), currency)

    return OrderEventDiscountObject(
        value=discount_obj.get("value"),
        amount=amount,
        value_type=discount_obj.get("value_type"),
        reason=discount_obj.get("reason"),
        old_value_type=discount_obj.get("old_value_type"),
        old_value=discount_obj.get("old_value"),
        old_amount=old_amount,
    )


def get_payment_status_for_order(order):
    status = ChargeStatus.NOT_CHARGED
    charged_money = order.total_charged

    if charged_money >= order.total.gross:
        status = ChargeStatus.FULLY_CHARGED
    elif charged_money and charged_money < order.total.gross:
        status = ChargeStatus.PARTIALLY_CHARGED
    return status


class OrderDiscount(graphene.ObjectType):
    value_type = graphene.Field(
        DiscountValueTypeEnum,
        required=True,
        description="Type of the discount: fixed or percent.",
    )
    value = PositiveDecimal(
        required=True,
        description="Value of the discount. Can store fixed value or percent value.",
    )
    reason = graphene.String(
        required=False, description="Explanation for the applied discount."
    )
    amount = graphene.Field(Money, description="Returns amount of discount.")


class OrderEventDiscountObject(OrderDiscount):
    old_value_type = graphene.Field(
        DiscountValueTypeEnum,
        required=False,
        description="Type of the discount: fixed or percent.",
    )
    old_value = PositiveDecimal(
        required=False,
        description="Value of the discount. Can store fixed value or percent value.",
    )
    old_amount = graphene.Field(
        Money, required=False, description="Returns amount of discount."
    )


class OrderEventOrderLineObject(graphene.ObjectType):
    quantity = graphene.Int(description="The variant quantity.")
    order_line = graphene.Field(lambda: OrderLine, description="The order line.")
    item_name = graphene.String(description="The variant name.")
    discount = graphene.Field(
        OrderEventDiscountObject, description="The discount applied to the order line."
    )


class OrderEvent(ModelObjectType[models.OrderEvent]):
    id = graphene.GlobalID(required=True)
    date = graphene.types.datetime.DateTime(
        description="Date when event happened at in ISO 8601 format."
    )
    type = OrderEventsEnum(description="Order event type.")
    user = graphene.Field(User, description="User who performed the action.")
    app = graphene.Field(
        App,
        description=(
            "App that performed the action. Requires of of the following permissions: "
            f"{AppPermission.MANAGE_APPS.name}, {OrderPermissions.MANAGE_ORDERS.name}, "
            f"{AuthorizationFilters.OWNER.name}."
        ),
    )
    message = graphene.String(description="Content of the event.")
    email = graphene.String(description="Email of the customer.")
    email_type = OrderEventsEmailsEnum(
        description="Type of an email sent to the customer."
    )
    amount = graphene.Float(description="Amount of money.")
    payment_id = graphene.String(
        description="The payment reference from the payment provider."
    )
    payment_gateway = graphene.String(description="The payment gateway of the payment.")
    quantity = graphene.Int(description="Number of items.")
    composed_id = graphene.String(description="Composed ID of the Fulfillment.")
    order_number = graphene.String(description="User-friendly number of an order.")
    invoice_number = graphene.String(
        description="Number of an invoice related to the order."
    )
    oversold_items = NonNullList(
        graphene.String, description="List of oversold lines names."
    )
    lines = NonNullList(OrderEventOrderLineObject, description="The concerned lines.")
    fulfilled_items = NonNullList(
        lambda: FulfillmentLine, description="The lines fulfilled."
    )
    warehouse = graphene.Field(
        Warehouse, description="The warehouse were items were restocked."
    )
    transaction_reference = graphene.String(
        description="The transaction reference of captured payment."
    )
    shipping_costs_included = graphene.Boolean(
        description="Define if shipping costs were included to the refund."
    )
    related_order = graphene.Field(
        lambda: Order, description="The order which is related to this order."
    )
    discount = graphene.Field(
        OrderEventDiscountObject, description="The discount applied to the order."
    )
    status = graphene.Field(
        TransactionStatusEnum, description="The status of payment's transaction."
    )
    reference = graphene.String(description="The reference of payment's transaction.")

    class Meta:
        description = "History log of the order."
        model = models.OrderEvent
        interfaces = [relay.Node]

    @staticmethod
    def resolve_user(root: models.OrderEvent, info):
        user_or_app = get_user_or_app_from_context(info.context)
        if not user_or_app:
            return None
        requester = user_or_app

        def _resolve_user(event_user):
            if (
                requester == event_user
                or requester.has_perm(AccountPermissions.MANAGE_USERS)
                or requester.has_perm(AccountPermissions.MANAGE_STAFF)
            ):
                return event_user
            return None

        if not root.user_id:
            return None

        return UserByUserIdLoader(info.context).load(root.user_id).then(_resolve_user)

    @staticmethod
    def resolve_app(root: models.OrderEvent, info):
        requestor = get_user_or_app_from_context(info.context)
        check_is_owner_or_has_one_of_perms(
            requestor,
            root.user,
            AppPermission.MANAGE_APPS,
            OrderPermissions.MANAGE_ORDERS,
        )
        return AppByIdLoader(info.context).load(root.app_id) if root.app_id else None

    @staticmethod
    def resolve_email(root: models.OrderEvent, _info):
        return root.parameters.get("email", None)

    @staticmethod
    def resolve_email_type(root: models.OrderEvent, _info):
        return root.parameters.get("email_type", None)

    @staticmethod
    def resolve_amount(root: models.OrderEvent, _info):
        amount = root.parameters.get("amount", None)
        return float(amount) if amount else None

    @staticmethod
    def resolve_payment_id(root: models.OrderEvent, _info):
        return root.parameters.get("payment_id", None)

    @staticmethod
    def resolve_payment_gateway(root: models.OrderEvent, _info):
        return root.parameters.get("payment_gateway", None)

    @staticmethod
    def resolve_quantity(root: models.OrderEvent, _info):
        quantity = root.parameters.get("quantity", None)
        return int(quantity) if quantity else None

    @staticmethod
    def resolve_message(root: models.OrderEvent, _info):
        return root.parameters.get("message", None)

    @staticmethod
    def resolve_composed_id(root: models.OrderEvent, _info):
        return root.parameters.get("composed_id", None)

    @staticmethod
    def resolve_oversold_items(root: models.OrderEvent, _info):
        return root.parameters.get("oversold_items", None)

    @staticmethod
    def resolve_order_number(root: models.OrderEvent, info):
        def _resolve_order_number(order: models.Order):
            return order.number

        return (
            OrderByIdLoader(info.context)
            .load(root.order_id)
            .then(_resolve_order_number)
        )

    @staticmethod
    def resolve_invoice_number(root: models.OrderEvent, _info):
        return root.parameters.get("invoice_number")

    @staticmethod
    @traced_resolver
    def resolve_lines(root: models.OrderEvent, info):
        raw_lines = root.parameters.get("lines", None)

        if not raw_lines:
            return None

        line_pks = []
        for entry in raw_lines:
            line_pk = entry.get("line_pk", None)
            if line_pk: