from typing import Tuple, Type

import graphene
from django.core.exceptions import ValidationError
from django.db.models import Model
from django.template.defaultfilters import truncatechars
from graphql import GraphQLError

from ...attribute import AttributeInputType
from ...attribute import models as attribute_models
from ...core.tracing import traced_atomic_transaction
from ...core.utils.editorjs import clean_editor_js
from ...discount import models as discount_models
from ...menu import models as menu_models
from ...page import models as page_models
from ...permission.enums import SitePermissions
from ...product import models as product_models
from ...shipping import models as shipping_models
from ...site.models import SiteSettings
from ..attribute.types import Attribute, AttributeValue
from ..channel import ChannelContext
from ..core import ResolveInfo
from ..core.descriptions import RICH_CONTENT
from ..core.enums import LanguageCodeEnum, TranslationErrorCode
from ..core.fields import JSONString
from ..core.mutations import BaseMutation, ModelMutation
from ..core.types import TranslationError
from ..core.utils import from_global_id_or_error
from ..discount.types import Sale, Voucher
from ..menu.types import MenuItem
from ..plugins.dataloaders import get_plugin_manager_promise
from ..product.types import Category, Collection, Product, ProductVariant
from ..shipping.types import ShippingMethodType
from ..shop.types import Shop
from ..site.dataloaders import get_site_promise
from . import types as translation_types

TRANSLATABLE_CONTENT_TO_MODEL = {
    str(
        translation_types.ProductTranslatableContent
    ): product_models.Product._meta.object_name,
    str(
        translation_types.CollectionTranslatableContent
    ): product_models.Collection._meta.object_name,
    str(
        translation_types.CategoryTranslatableContent
    ): product_models.Category._meta.object_name,
    str(
        translation_types.AttributeTranslatableContent
    ): attribute_models.Attribute._meta.object_name,
    str(
        translation_types.AttributeValueTranslatableContent
    ): attribute_models.AttributeValue._meta.object_name,
    str(
        translation_types.ProductVariantTranslatableContent
    ): product_models.ProductVariant._meta.object_name,
    # Page Translation mutation reverses model and TranslatableContent
    page_models.Page._meta.object_name: str(translation_types.PageTranslatableContent),
    str(
        translation_types.ShippingMethodTranslatableContent
    ): shipping_models.ShippingMethod._meta.object_name,
    str(
        translation_types.SaleTranslatableContent
    ): discount_models.Sale._meta.object_name,
    str(
        translation_types.VoucherTranslatableContent
    ): discount_models.Voucher._meta.object_name,
    str(
        translation_types.MenuItemTranslatableContent
    ): menu_models.MenuItem._meta.object_name,
}


def validate_input_against_model(model: Type[Model], input_data: dict):
    data_to_validate = {key: value for key, value in input_data.items() if value}
    instance = model(**data_to_validate)
    all_fields = [field.name for field in model._meta.fields]
    exclude_fields = set(all_fields) - set(data_to_validate)
    instance.full_clean(exclude=exclude_fields, validate_unique=False)


class BaseTranslateMutation(ModelMutation):
    class Meta:
        abstract = True

    @classmethod
    def clean_node_id(cls, id: str) -> Tuple[str, Type[graphene.ObjectType]]:
        if not id:
            raise ValidationError(
                {"id": ValidationError("This field is required", code="required")}
            )

        try:
            node_type, node_pk = from_global_id_or_error(id)
        except GraphQLError:
            raise ValidationError(
       