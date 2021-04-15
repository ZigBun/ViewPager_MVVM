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
        description="Associated attribute that can be