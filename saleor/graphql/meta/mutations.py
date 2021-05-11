import logging
from typing import List, cast

import graphene
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import DatabaseError
from graphql.error.base import GraphQLError

from ...checkout import models as checkout_models
from ...checkout.models import Checkout
from ...core import models
from ...core.error_codes import MetadataErrorCode
from ...core.exceptions import PermissionDenied
from ...discount import models as discount_models
from ...menu import models as menu_models
from ...order import models as order_models
from ...product import models as product_models
from ...shipping import models as shipping_models
from ..channel import ChannelContext
from ..core import ResolveInfo
from ..core.mutations import BaseMutation
from ..core.types import MetadataError, NonNullList
from ..core.utils import from_global_id_or_error
from ..payment.utils import metadata_contains_empty_key
from .extra_methods import MODEL_EXTRA_METHODS, MODEL_EXTRA_PREFETCH
from .permissions import (
    PRIVATE_META_PERMISSION_MAP,
    PUBLIC_META_PERMISSION_MAP,
    AccountPermissions,
)
from .types import ObjectWithMetadata, get_valid_metadata_instance

logger = logging.getLogger(__name__)


def _save_instance(instance, metadata_field: str):
    fields = [metadata_field]

    try:
        if bool(instance._meta.get_field("updated_at")):
            fields.append("updated_at")
    except FieldDoesNotExist:
        pass

    try:
        instance.save(update_fields=fields)
    except DatabaseError:
        msg = "Cannot update metadata for instance. Updating not existing object."
        raise ValidationError(
            {"metadata": ValidationError(msg, code=MetadataErrorCode.NOT_FOUND.value)}
        )


class MetadataPermissionOptions(graphene.types.mutation.MutationOptions):
    permission_map = {}


class BaseMetadataMutation(BaseMutation):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls,
        arguments=None,
        permission_map=[],
        _meta=None,
        **kwargs,
    ):
        if not _meta:
            _meta = MetadataPermissionOptions(cls)
        if not arguments:
            arguments = {}
        fields = {"item": graphene.Field(ObjectWithMetadata)}

        _meta.permission_map = permission_map

        super().__init_subclass_with_meta__(_meta=_meta, **kwargs)
        cls._update_mutation_arguments_and_fields(arguments=arguments, fields=fields)

    @classmethod
    def get_instance(cls, info: ResolveInfo, /, *, id: str, qs=None, **kwargs):
        try:
            type_name, _ = from_global_id_or_error(id)
            # ShippingMethodType represents the ShippingMethod model
            if type_name == "ShippingMethodType":
                qs = shipping_models.ShippingMethod.objects

            return cls.get_node_or_error(info, id, qs=qs)
        except GraphQLError as e:
            if instance := cls.get_instance_by_token(id, qs):
                return instance
            raise ValidationError(
                {
                    "id": ValidationError(
                        str(e), code=MetadataErrorCode.GRAPHQL_ERROR.value
                    )
                }
            )

    @classmethod
    def get_instance_by_token(cls, object_id, qs):
        if not qs:
            if order := order_models.Order.objects.filter(id=object_id).first():
                return order
            if checkout := checkout_models.Checkout.objects.filter(
                token=object_id
            ).first():
                return checkout
            return None
        if qs and "token" in [field.name for field in qs.model._meta.get_fields()]:
            return qs.filter(token=object_id).first()

    @classmethod
    def validate_model_is_model_with_metadata(cls, model, object_id):
        if not issubclass(model, models.ModelWithMetadata) and not model == Checkout:
            raise ValidationError(
                {
                    "id": ValidationError(
                        f"Couldn't resolve to a item with meta: {object_id}",
                        code=MetadataErrorCode.NOT_FOUND.value,
                    )
                }
            )

    @classmethod
    def validate_metadata_keys(cls, metadata_list: List[dict]):
        if metadata_contains_empty_key(metadata_list):
            raise ValidationError(
                {
                    "input": ValidationError(
              