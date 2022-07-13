from typing import TYPE_CHECKING, TypeVar, Union

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Exists, F, OrderBy, OuterRef, Q

from ...core.db.fields import SanitizedJSONField
from ...core.models import ModelWithExternalReference, ModelWithMetadata, SortableModel
from ...core.units import MeasurementUnits
from ...core.utils.editorjs import clean_editor_js
from ...core.utils.translations import Translation, TranslationProxy
from ...page.models import Page, PageType
from ...permission.enums import PageTypePermissions, ProductTypePermissions
from ...permission.utils import has_one_of_permissions
from ...product.models import Product, ProductType, ProductVariant
from .. import AttributeEntityType, AttributeInputType, AttributeType

if TYPE_CHECKING:
    from ...account.models import User
    from ...app.models import App


class BaseAssignedAttribute(models.Model):
    class Meta:
        abstract = True

    @property
    def attribute(self):
        return self.assignment.attribute  # type: ignore[attr-defined] # mixin


T = TypeVar("T", bound=models.Model)


class BaseAttributeQuerySet(models.QuerySet[T]):
    def get_public_attributes(self):
        raise NotImplementedError

    def get_visible_to_user(self, requestor: Union["User", "App", None]):
        if has_one_of_permissions(
            requestor,
            [
                PageTypePermissions.MANAGE_PAGE_TYPES_AND_ATTRIBUTES,
                ProductTypePermissions.MANAGE_PRODUCT_TYPES_AND_ATTRIBUTES,
            ],
        ):
            return self.all()
        return self.get_public_attributes()


class AssociatedAttributeQuerySet(BaseAttributeQuerySet[T]):
    def get_public_attributes(self):
        attributes = Attribute.o