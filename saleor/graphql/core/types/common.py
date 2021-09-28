from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

import graphene
from django.core.files.storage import default_storage

from ....core.utils import build_absolute_uri
from ...account.enums import AddressTypeEnum
from ..descriptions import (
    ADDED_IN_36,
    ADDED_IN_312,
    DEPRECATED_IN_3X_FIELD,
    PREVIEW_FEATURE,
)
from ..enums import (
    AccountErrorCode,
    AppErrorCode,
    AttributeErrorCode,
    ChannelErrorCode,
    CheckoutErrorCode,
    CollectionErrorCode,
    DiscountErrorCode,
    ExportErrorCode,
    ExternalNotificationTriggerErrorCode,
    GiftCardErrorCode,
    GiftCardSettingsErrorCode,
    InvoiceErrorCode,
    JobStatusEnum,
    LanguageCodeEnum,
    MenuErrorCode,
    MetadataErrorCode,
    OrderErrorCode,
    OrderSettingsErrorCode,
    PageErrorCode,
    PaymentErrorCode,
    PermissionEnum,
    PermissionGroupErrorCode,
    PluginErrorCode,
    ProductErrorCode,
    ProductVariantBulkErrorCode,
    ShippingErrorCode,
    ShopErrorCode,
    StockBulkUpdateErrorCode,
    StockErrorCode,
    ThumbnailFormatEnum,
    TimePeriodTypeEnum,
    TransactionCreateErrorCode,
    TransactionRequestActionErrorCode,
    TransactionUpdateErrorCode,
    TranslationErrorCode,
    UploadErrorCode,
    WarehouseErrorCode,
    WebhookDryRunErrorCode,
    WebhookErrorCode,
    WebhookTriggerErrorCode,
    WeightUnitsEnum,
)
from ..scalars import Date, PositiveDecimal
from ..tracing import traced_resolver
from .money import VAT
from .upload import Upload

if TYPE_CHECKING:
    from .. import ResolveInfo

# deprecated - this is temporary constant that contains the graphql types
# which has double id available - uuid and old int id
TYPES_WITH_DOUBLE_ID_AVAILABLE = ["Order", "OrderLine", "OrderDiscount", "CheckoutLine"]


class NonNullList(graphene.List):
    """A list type that automatically adds non-null constraint on contained items."""

    def __init__(self, of_type, *args, **kwargs):
        of_type = graphene.NonNull(of_type)
        super(NonNullList, self).__init__(of_type, *args, **kwargs)


class CountryDisplay(graphene.ObjectType):
    code = graphene.String(description="Country code.", required=True)
    country = graphene.String(description="Country name.", required=True)
    vat = graphene.Field(
        VAT,
        description="Country tax.",
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Use `TaxClassC