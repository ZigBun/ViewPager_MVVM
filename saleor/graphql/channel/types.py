import collections
import itertools
from typing import TYPE_CHECKING, Dict, List, Type, TypeVar, Union, cast

import graphene
from django.db.models import Model
from django_countries.fields import Country
from graphene.types.objecttype import ObjectType
from graphene.types.resolver import get_default_resolver
from promise import Promise

from ...channel import models
from ...core.models import ModelWithMetadata
from ...permission.auth_filters import AuthorizationFilters
from ...permission.enums import ChannelPermissions, OrderPermissions
from ..account.enums import CountryCodeEnum
from ..core import ResolveInfo
from ..core.descriptions import (
    ADDED_IN_31,
    ADDED_IN_35,
    ADDED_IN_36,
    ADDED_IN_37,
    ADDED_IN_312,
    PREVIEW_FEATURE,
)
from ..core.fields import PermissionsField
from ..core.types import CountryDisplay, ModelObjectType, NonNullList
from ..meta.types import ObjectWithMetadata
from ..translations.resolvers import resolve_translation
from ..warehouse.dataloaders import WarehousesByChannelIdLoader
from ..warehouse.types import Warehouse
from . import ChannelContext
from .dataloaders import ChannelWithHasOrdersByIdLoader
from .enums import AllocationStrategyEnum

if TYPE_CHECKING:
    from ...shipping.models import ShippingZone


T = TypeVar("T", bound=Model)


class ChannelContextTypeForObjectType(ModelObjectType[T]):
    """A Graphene type that supports resolvers' root as ChannelContext objects."""

    class Meta:
        abstract = True

    @staticmethod
    def resolver_with_context(
        attname, default_value, root: ChannelContext, info: ResolveInfo, **args
    ):
        resolver = get_default_resolver()
        return resolver(attname, default_value, root.node, info, **args)

    @staticmethod
    def resolve_id(root: ChannelContext[T], _info: ResolveInfo):
        return root.node.pk

    @staticmethod
    def resolve_translation(
        root: ChannelContext[T], info: ResolveInfo, *, language_code
    ):
        # Resolver for TranslationField; needs to be manually specified.
        return resolve_translation(root.node, info, language_code=language_code)


class ChannelContextType(ChannelContextTypeForObjectType[T]):
    """A Graphene type that supports resolvers' root as ChannelContext objects."""

    class Meta:
        abstract = True

    @classmethod
    def is_type_of(cls, root: Union[ChannelContext[T], T], _info: ResolveInfo) -> bool:
        # Unwrap node 