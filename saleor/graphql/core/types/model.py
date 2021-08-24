import copy
from typing import Generic, Optional, Type, TypeVar
from uuid import UUID

from django.db.models import Model, Q
from graphene.types.objecttype import ObjectType, ObjectTypeOptions

from ..descriptions import ADDED_IN_33, PREVIEW_FEATURE
from . import TYPES_WITH_DOUBLE_ID_AVAILABLE


class ModelObjectOptions(ObjectTypeOptions):
    model = None
    metadata_since = None


MT = TypeVar("MT", bound=Model)


class ModelObjectType(Generic[MT], ObjectType):
    @classmethod
    def __init_subclass_with_meta__(
        cls,
        interfaces=(),
        possible_types=(),
        default_resolver=None,
        _meta=None,
        **options,
    ):
        if not _meta:
            _meta = ModelObjectOptions(cls)

        if not 