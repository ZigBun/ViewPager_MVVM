from collections import defaultdict
from typing import cast

import graphene
from babel.core import get_global
from django.core.exceptions import ValidationError
from django.db.models import F
from graphene.types import InputObjectType
from graphene.utils.str_converters import to_camel_case

from ....attribute import AttributeType
from ....core.tracing import traced_atomic_transaction
from ....permission.enums import ProductPermissions
from ....product import models
from ....product.error_codes import ProductVariantBulkErrorCode
from ....product.search import update_product_search_vector
from ....product.tasks import update_product_discounted_price_task
from ....warehouse import models as warehouse_models
from ...attribute.types import (
    AttributeValueDescriptions,
    AttributeValueSelectableTypeInput,
)
from ...attribute.utils import AttributeAssignmentMixin
from ...channel import ChannelContext
from ...core.descriptions import (
    ADDED_IN_311,
    ADDED_IN_312,
    DEPRECATED_IN_3X_FIELD,
    PREVIEW_FEATURE,
)
from ...core.enums import ErrorPolicyEnum
from ...core.fields import JSONString
from ...core.mutations import (
    BaseMutation,
    ModelMutation,
    validation_error_to_error_type,
)
from ...core.scalars import Date
from ...core.types import BulkProductError, NonNullList, ProductVariantBulkError
from ...core.utils import get_duplicated_values
from ...core.validators import validate_price_precision
from ...plugins.dataloaders import get_plugin_manager_promise
from ..mutations.channels import ProductVariantChannelListingAddInput
from ..mutations.product.product_create import StockInput
from ..mutations.product_variant.product_variant_create import (
    ProductVariantCreate,
    ProductVariantInput,
)
from ..types import ProductVariant
from ..utils import clean_variant_sku, get_used_variants_attribute_values

CURRENCY_FRACTIONS = get_global("currency_fractions")


def clean_price(
    price,
    field_name,
    currency,
    channel_id,
    variant_index,
    errors,
    index_error_map,
):
    try:
        validate_price_precision(price, currency, CURRENCY_FRACTIONS)
    except ValidationError as error:
        index_error_map[variant_index].append(
            ProductVariantBulkError(
                field=to_camel_case(field_name),
                message=error.message,
                code=ProductVariantBulkErrorCode.INVALID_PRICE.value,
                channels=[channel_id],
            )
        )
        if errors is not None:
            error.code = ProductVariantBulkErrorCode.INVALID_PRICE.value
            error.params = {
                "channels": [channel_id],
                "index": variant_index,
            }
            errors[field_name].append(error)


def get_results(instances_data_with_errors_list, reject_everything=False):
    if reject_everything:
        return [
            ProductVariantBulkResult(product_variant=None, errors=data.get("errors"))
            for data in instances_data_with_errors_list
        ]
    return [
        ProductVariantBulkResult(
            product_variant=ChannelContext(
                node=data.get("instance"), channel_slug=None
            ),
            errors=data.get("errors"),
        )
        if data.get("instance")
        else ProductVariantBulkResult(product_variant=None, errors=data.get("errors"))
        for data in instances_data_with_errors_list
    ]


class ProductVariantBulkResult(graphene.ObjectType):
    product_variant = graphene.Field(
        ProductVariant, required=False, description="Product variant data."
    )
    errors = NonNullList(
        ProductVariantBulkError,
        required=False,
        description="List of errors occurred on create attempt.",
    )


class BulkAttributeValueInput(InputObjectType):
    id = graphene.ID(description="ID of the selected attribute.")
    values = NonNullList(
        graphene.String,
        required=False,
        description=(
            "The value or slug of an attribute to resolve. "
            "If the passed value is non-existent, it will be created."
            + DEPRECATED_IN_3X_FIELD
        ),
    )
    dropdown = AttributeValueSelectableTypeInput(
        required=False,
        description="Attribute value ID." + ADDED_IN_312,
    )
    swatch = AttributeValueSelectableTypeInput(
        required=False,
        description="Attribute value ID." + ADDED_IN_312,
    )
    multiselect = NonNullList(
        AttributeValueSelectableTypeInput,
        required=False,
        description="List of attribute value IDs." + ADDED_IN_312,
    )
    numeric = graphene.String(
        required=False,
        description="Numeric value of an attribute." + ADDED_IN_312,
    )
    file = graphene.String(
        required=False,
        description=(
            "URL of the file attribute. Every time, a new value is created."
            + ADDED_IN_312
        ),
    )
    content_type = graphene.String(
        required=False,
        description="File content type." + ADDED_IN_312,
    )
    references = NonNullList(
        graphene.ID,
        description=(
            "List of entity IDs that will be used as references." + ADDED_IN_312
        ),
        required=False,
    )
    rich_text = JSONString(
        required=False,
        description="Text content in JSON format." + ADDED_IN_312,
    )
    plain_text = graphene.String(
        required=False,
        description="Plain text content." + ADDED_IN_312,
    )
    boolean = graphene.Boolean(
        required=False,
        description=(
            "The boolean value of an attribute to resolve. "
            "If the passed value is non-existent, it will be created."
        ),
    )
    date = Date(
        required=False, description=AttributeValueDescriptions.DATE + ADDED_IN_312
    )
    date_time = graphene.DateTime(
        required=False, description=AttributeValueDescriptions.DATE_TIME + ADDED_IN_312
    )


class ProductVariantBulkCreateInput(ProductVariantInput):
    attributes = NonNullList(
        BulkAttributeValueInput,
        required=True,
        description="List of attributes specific to this variant.",
    )
    stocks = NonNullList(
        StockInput,
        description="Stocks of a product available for sale.",
        required=False,
    )
    channel_listings = NonNullList(
        ProductVariantChannelListingAddInput,
        description="List of prices assigned to channels.",
        required=False,
    )
    sku = graphene.String(description="Stock keeping unit.")


class ProductVariantBulkCreate(BaseMutation):
    count = graphene.Int(
        required=True,
        default_value=0,
        description="Returns how many objects were created.",
    )
    product_variants = NonNullList(
        ProductVariant,
        required=True,
        default_value=[],
        description="List of the created variants." + DEPRECATED_IN_3X_FIELD,
    )

    results = NonNullList(
        ProductVariantBulkResult,
        required=True,
        default_value=[],
        description="List of the created variants." + ADDED_IN_311,
    )

    class Arguments:
        variants = NonNullList(
            ProductVar