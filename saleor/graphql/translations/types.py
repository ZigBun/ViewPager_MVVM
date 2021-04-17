from typing import List, TypeVar

import graphene
from django.conf import settings
from django.db.models import Model

from ...attribute import AttributeInputType
from ...attribute import models as attribute_models
from ...attribute.models import AttributeValue
from ...discount import models as discount_models
from ...menu import models as menu_models
from ...page import models as page_models
from ...permission.enums import DiscountPermissions, ShippingPermissions
from ...product import models as product_models
from ...shipping import models as shipping_models
from ...site import models as site_models
from ..attribute.dataloaders import AttributesByAttributeId
from ..channel import ChannelContext
from ..core.descriptions import ADDED_IN_39, DEPRECATED_IN_3X_FIELD, RICH_CONTENT
from ..core.enums import LanguageCodeEnum
from ..core.fields import JSONString, PermissionsField
from ..core.tracing import traced_resolver
from ..core.types import LanguageDisplay, ModelObjectType, NonNullList
from ..core.utils import str_to_enum
from ..page.dataloaders import SelectedAttributesByPageIdLoader
from ..product.dataloaders import (
    SelectedAttributesByProductIdLoader,
    SelectedAttributesByProductVariantIdLoader,
)
from .fields import TranslationField


def get_translatable_attribute_values(attributes: list) -> List[AttributeValue]:
    """Filter the list of passed attributes.

    Return those which are translatable attributes.
    """
    translatable_values: List[AttributeValue] = []
    for assignment in attributes:
        attr = assignment["attribute"]
        if attr.input_type in AttributeInputType.TRANSLATABLE_ATTRIBUTES:
            translatable_values.extend(assignment["values"])
    return translatable_values


T = TypeVar("T", bound=Model)


class BaseTranslationType(ModelObjectType[T]):
    language = graphene.Field(
        LanguageDisplay, description="Translation language.", required=True
    )

    class Meta:
        abstract = True

    @staticmethod
    @traced_resolver
    def resolve_language(root, _info):
        try:
            language = next(
                language[1]
                for language in settings.LANGUAGES
                if language[0] == root.language_code
            )
        except StopIteration:
            return None
        return LanguageDisplay(
            code=LanguageCodeEnum[str_to_enum(root.language_code)], language=language
        )


class AttributeValueTranslation(
    BaseTranslationType[attribute_models.AttributeValueTranslation]
):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)
    rich_text = JSONString(description="Attribute value." + RICH_CONTENT)
    plain_text = graphene.String(description="Attribute plain text value.")

    class Meta:
        model = attribute_models.AttributeValueTranslation
        interfaces = [graphene.relay.Node]


class AttributeTranslation(BaseTranslationType[attribute_models.AttributeTranslation]):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)

    class Meta:
        model = attribute_models.AttributeTranslation
        interfaces = [graphene.relay.Node]


class AttributeTranslatableContent(ModelObjectType[attribute_models.Attribute]):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)
    translation = TranslationField(AttributeTranslation, type_name="attribute")
    attribute = graphene.Field(
        "saleor.graphql.attribute.types.Attribute",
        description="Custom attribute of a product.",
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Get model fields from the root level queries."
        ),
    )

    class Meta:
        model = attribute_models.Attribute
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_attribute(root: attribute_models.Attribute, _info):
        return root


class AttributeValueTranslatableContent(
    ModelObjectType[attribute_models.AttributeValue]
):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)
    rich_text = JSONString(description="Attribute value." + RICH_CONTENT)
    plain_text = graphene.String(description="Attribute plain text value.")
    translation = TranslationField(
        AttributeValueTranslation, type_name="attribute value"
    )
    attribute_value = graphene.Field(
        "saleor.graphql.attribute.types.AttributeValue",
        description="Represents a value of an attribute.",
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Get model fields from the root level queries."
        ),
    )
    attribute = graphene.Field(
        AttributeTranslatableContent,
        description="Associated attribute that can be translated." + ADDED_IN_39,
    )

    class Meta:
        model = attribute_models.AttributeValue
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_attribute_value(root: attribute_models.AttributeValue, _info):
        return root

    @staticmethod
    def resolve_attribute(root: attribute_models.AttributeValue, info):
        return AttributesByAttributeId(info.context).load(root.attribute_id)


class ProductVariantTranslation(
    BaseTranslationType[product_models.ProductVariantTranslation]
):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)

    class Meta:
        model = product_models.ProductVariantTranslation
        interfaces = [graphene.relay.Node]


class ProductVariantTranslatableContent(ModelObjectType[product_models.ProductVariant]):
    id = graphene.GlobalID(required=True)
    name = graphene.String(required=True)
    translation = TranslationField(
        ProductVariantTranslation, type_name="product variant"
    )
    product_variant = graphene.Field(
        "saleor.graphql.product.types.products.ProductVariant",
        description=(
            "Represents a version of a product such as different size or color."
        ),
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Get model fields from the root level queries."
        ),
    )
    attribute_values = NonNullList(
        AttributeValueTranslatableContent,
        required=True,
        description="List of product variant attribute values that can be translated.",
    )

    class Meta:
        model = product_models.ProductVariant
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_product_variant(root: product_models.ProductVariant, info):
        return ChannelContext(node=root, channel_slug=None)

    @staticmethod
    def resolve_attribute_values(root: product_models.ProductVariant, info):
        return (
            SelectedAttributesByProductVariantIdLoader(info.context)
            .load(root.id)
            .then(get_translatable_attribute_values)
        )


class ProductTranslation(BaseTranslationType[product_models.ProductTranslation]):
    id = graphene.GlobalID(required=True)
    seo_title = graphene.String()
    seo_description = graphene.String()
    name = graphene.String()
    description = JSONString(
        description="Translated description of the product." + RICH_CONTENT
    )
    description_json = JSONString(
        description="Translated description of the product." + RICH_CONTENT,
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Use the `description` field instead."
        ),
    )

    class Meta:
        model = product_models.ProductTranslation
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_description_json(root: product_models.ProductTranslation, _info):
        description = root.description
        return description if description is not None else {}


class ProductTranslatableContent(ModelObjectType[product_models.Product]):
    id = graphene.GlobalID(required=True)
    seo_title = graphene.String()
    seo_description = graphene.String()
    name = graphene.String(required=True)
    description = JSONString(description="Description of the product." + RICH_CONTENT)
    description_json = JSONString(
        description="Description of the product." + RICH_CONTENT,
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Use the `description` field instead."
        ),
    )
    translation = TranslationField(ProductTranslation, type_name="product")
    product = graphene.Field(
        "saleor.graphql.product.types.products.Product",
        description="Represents an individual item for sale in the storefront.",
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Get model fields from the root level queries."
        ),
    )
    attribute_values = NonNullList(
        AttributeValueTranslatableContent,
        required=True,
        description="List of product attribute values that can be translated.",
    )

    class Meta:
        model = product_models.Product
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_product(root: product_models.Product, info):
        return ChannelContext(node=root, channel_slug=None)

    @staticmethod
    def resolve_description_json(root: product_models.Product, _info):
        description = root.description
        return description if description is not None else {}

    @staticmethod
    def resolve_attribute_values(root: product_models.Product, info):
        return (
            SelectedAttributesByProductIdLoader(info.context)
            .load(root.id)
            .then(get_translatable_attribute_values)
        )


class CollectionTranslation(BaseTranslationType[product_models.CollectionTranslation]):
    id = graphene.GlobalID(required=True)
    seo_title = graphene.String()
    seo_description = graphene.String()
    name = graphene.String()
    description = JSONString(
        description="Translated description of the collection." + RICH_CONTENT
    )
    description_json = JSONString(
        description="Translated description of the collection." + RICH_CONTENT,
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Use the `description` field instead."
        ),
    )

    class Meta:
        model = product_models.CollectionTranslation
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_description_json(root: product_models.CollectionTranslation, _info):
        description = root.description
        return description if description is not None else {}


class CollectionTranslatableContent(ModelObjectType[product_models.Collection]):
    id = graphene.GlobalID(required=True)
    seo_title = graphene.String()
    seo_description = graphene.String()
    name = graphene.String(required=True)
    description = JSONString(
        description="Description of the collection." + RICH_CONTENT
    )
    description_json = JSONString(
        description="Description of the collection." + RICH_CONTENT,
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Use the `description` field instead."
        ),
    )
    translation = TranslationField(CollectionTranslation, type_name="collection")
    collection = graphene.Field(
        "saleor.graphql.product.types.collections.Collection",
        description="Represents a collection of products.",
        deprecation_reason=(
            f"{DEPRECATED_IN_3X_FIELD} Get model fields from the root level queries."
        ),
    )

    class Meta:
        model = product_models.Collection
        interfaces = [graphene.relay.Node]

    @staticmethod
    def resolve_collection(root: product_models.Collection, info):
        collection = product_models.Collection.objects.all().filter(pk=root.id).first()
        return (
            ChannelContext(node=collection, channel_slug=None) if collection else None
        )

    @staticmethod
    def resolve_description_json(root: product_models.Collection, _info):
        description = root.description
        return description if description is not None else {}


class CategoryTranslation(BaseTranslationType[product_models.CategoryTranslation]):
    id = graphene.GlobalID(required=True)
    seo_title = graphene.String()
    seo_description = graphene.String()
    name = graphene.String()
    description = JSONString(
        description="Translated description of the category." + RICH_CONTENT
    )
    description_json = JSONString(
        description="Tran