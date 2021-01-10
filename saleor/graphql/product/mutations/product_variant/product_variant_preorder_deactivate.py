import graphene
from django.core.exceptions import ValidationError

from .....core.exceptions import PreorderAllocationError
from .....core.tracing import traced_atomic_transaction
from .....permission.enums import ProductPermissions
from .....product import models
from .....product.error_codes import ProductErrorCode
from .....warehouse.management import deactivate_preorder_for_variant
from ....channel import ChannelContext
from ....core import ResolveInfo
from ....core.descriptions import ADDED_IN_31, PREVIEW_FEATURE
from ....core.mutations import BaseMutation
from ....core.types import ProductError
from ....plugins.dataloaders import get_plugin_manager_promise
from ...types import ProductVariant


class ProductVariantPreorderDeactivate(BaseMutation):
    product_variant = graphene.Field(
        ProductVariant, description="Product variant with ended preorder."
    )

    class Arguments:
        id = graphene.ID(
            required=True,
            description="ID of a variant which preorder should be deactivated.",
        )

    class Meta:
        description = (
            "Deactivates product variant preorder. "
            "It changes all preorder allocation into regular allocation."
            + ADDED_IN_31
            + PREVIEW_FEATURE
        )
        permissions = (ProductPermissions.MANAGE_PRODUCTS,)
        error_type_class = ProductError

    @classmethod
    def perform_mutation(  # type: ignore[override]
        cls, _root, info: ResolveInfo, /, *, id
    ):
        qs = models.ProductVariant.objects.prefetched_for_webhook()
        variant = cls.get_node_or_error(
            info, id, field="id", only_type=ProductVariant, qs=qs
        )
        if not variant.is_p