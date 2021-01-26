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
            ProductVariantBulkCreateInput,
            required=True,
            description="Input list of product variants to create.",
        )
        product_id = graphene.ID(
            description="ID of the product to create the variants for.",
            name="product",
            required=True,
        )
        error_policy = ErrorPolicyEnum(
            required=False,
            default_value=ErrorPolicyEnum.REJECT_EVERYTHING.value,
            description=(
                "Policies of error handling. DEFAULT: "
                + ErrorPolicyEnum.REJECT_EVERYTHING.name
                + ADDED_IN_311
                + PREVIEW_FEATURE
            ),
        )

    class Meta:
        description = "Creates product variants for a given product."
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = BulkProductError
        error_type_field = "bulk_product_errors"
        support_meta_field = True
        support_private_meta_field = True

    @classmethod
    def clean_attributes(
        cls,
        cleaned_input,
        product_type,
        variant_attributes,
        variant_attributes_ids,
        used_attribute_values,
        errors,
        variant_index,
        index_error_map,
    ):
        attributes_errors_count = 0
        if attributes_input := cleaned_input.get("attributes"):
            attributes_ids = {attr["id"] for attr in attributes_input or []}
            invalid_attributes = attributes_ids - variant_attributes_ids
            if len(invalid_attributes) > 0:
                message = "Given attributes are not a variant attributes."
                code = ProductVariantBulkErrorCode.ATTRIBUTE_CANNOT_BE_ASSIGNED.value
                index_error_map[variant_index].append(
                    ProductVariantBulkError(
                        field="attributes", message=message, code=code
                    )
                )
                if errors is not None:
                    errors["attributes"].append(
                        ValidationError(
                            message,
                            code=code,
                            params={
                                "attributes": invalid_attributes,
                                "index": variant_index,
                            },
                        )
                    )
                attributes_errors_count += 1

            if product_type.has_variants:
                try:
                    cleaned_attributes = AttributeAssignmentMixin.clean_input(
                        attributes_input, variant_attributes
                    )
                    ProductVariantCreate.validate_duplicated_attribute_values(
                        cleaned_attributes, used_attribute_values, None
                    )
                    cleaned_input["attributes"] = cleaned_attributes
                except ValidationError as exc:
                    for error in exc.error_list:
                        attributes = (
                            error.params.get("attributes") if error.params else None
                        )
                        index_error_map[variant_index].append(
                            ProductVariantBulkError(
                                field="attributes",
                                message=error.message,
                                code=error.code,
                                attributes=attributes,
                            )
                        )
                    if errors is not None:
                        exc.params = {"index": variant_index}
                        errors["attributes"].append(exc)
                    attributes_errors_count += 1
            else:
                message = "Cannot assign attributes for product type without variants"
                index_error_map[variant_index].append(
                    ProductVariantBulkError(
                        field="attributes",
                        message=message,
                        code=ProductVariantBulkErrorCode.INVALID.value,
                    )
                )
                if errors is not None:
                    errors["attributes"].append(
                        ValidationError(
                            message,
                            code=ProductVariantBulkErrorCode.INVALID.value,
                            params={
                                "attributes": invalid_attributes,
                                "index": variant_index,
                            },
                        )
                    )
                attributes_errors_count += 1
        return attributes_errors_count

    @classmethod
    def clean_prices(
        cls,
        price,
        cost_price,
        currency_code,
        channel_id,
        variant_index,
        errors,
        index_error_map,
    ):
        clean_price(
            price,
            "price",
            currency_code,
            channel_id,
            variant_index,
            errors,
            index_error_map,
        )
        clean_price(
            cost_price,
            "cost_price",
            currency_code,
            channel_id,
            variant_index,
            errors,
            index_error_map,
        )

    @classmethod
    def clean_channel_listings(
        cls,
        channel_listings,
        product_channel_global_id_to_instance_map,
        errors,
        variant_index,
        index_error_map,
    ):
        channel_ids = [
            channel_listing["channel_id"] for channel_listing in channel_listings
        ]
        listings_to_create = []

        duplicates = get_duplicated_values(channel_ids)
        if duplicates:
            message = "Duplicated channel ID."
            index_error_map[variant_index].append(
                ProductVariantBulkError(
                    field="channelListings",
                    message=message,
                    code=ProductVariantBulkErrorCode.DUPLICATED_INPUT_ITEM.value,
                    channels=duplicates,
                )
            )
            if errors is not None:
                errors["channel_listings"] = ValidationError(
                    message=message,
                    code=ProductVariantBulkErrorCode.DUPLICATED_INPUT_ITEM.value,
                    params={"channels": duplicates, "index": variant_index},
                )

        channels_not_assigned_to_product = [
            channel_id
            for channel_id in channel_ids
            if channel_id not in product_channel_global_id_to_instance_map.keys()
        ]

        if channels_not_assigned_to_product:
            message = "Product not available in channels."
            code = ProductVariantBulkErrorCode.PRODUCT_NOT_ASSIGNED_TO_CHANNEL.value
            index_error_map[variant_index].append(
                ProductVariantBulkError(
                    field="channelId",
                    message=message,
                    code=code,
                    channels=channels_not_assigned_to_product,
                )
            )
            if errors is not None:
                errors["channel_id"].append(
                    ValidationError(
                        message=message,
                        code=code,
                        params={
                            "index": variant_index,
                            "channels": channels_not_assigned_to_product,
                        },
                    )
                )

        for channel_listing in channel_listings:
            channel_id = channel_listing["channel_id"]

            if (
                channel_id in channels_not_assigned_to_product
                or channel_id in duplicates
            ):
                continue

            channel_listing["ch