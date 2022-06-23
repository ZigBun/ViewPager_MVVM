from collections import defaultdict
from typing import List, Tuple

import graphene
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .....attribute import AttributeInputType
from .....attribute import models as attribute_models
from .....core.tracing import traced_atomic_transaction
from .....permission.enums import ProductPermissions
from .....product import models
from .....product.error_codes import ProductErrorCode
from .....product.search import update_product_search_vector
from .....product.tasks import update_product_discounted_price_task
from .....product.utils.variants import generate_and_set_variant_name
from ....attribute.types import AttributeValueInput
from ....attribute.utils import AttributeAssignmentMixin, AttrValuesInput
from ....channel import ChannelContext
from ....core import ResolveInfo
from ....core.descriptions import (
    ADDED_IN_31,
    ADDED_IN_38,
    ADDED_IN_310,
    PREVIEW_FEATURE,
)
from ....core.mutations import ModelMutation
from ....core.scalars import WeightScalar
from ....core.types import NonNullList, ProductError
from ....core.utils import get_duplicated_values
from ....meta.mutations import MetadataInput
from ....plugins.dataloaders import get_plugin_manager_promise
from ....warehouse.types import Warehouse
from ...types import ProductVariant
from ...utils import (
    clean_variant_sku,
    create_stocks,
    get_used_variants_attribute_values,
)
from ..product.product_create import StockInput

T_INPUT_MAP = List[Tuple[attribute_models.Attribute, AttrValuesInput]]


class PreorderSettingsInput(graphene.InputObjectType):
    global_threshold = graphene.Int(
        description="The global threshold for preorder variant."
    )
    end_date = graphene.DateTime(description="The end date for preorder.")


class ProductVariantInput(graphene.InputObjectType):
    attributes = NonNullList(
        AttributeValueInput,
        required=False,
        description="List of attributes specific to this variant.",
    )
    sku = graphene.String(description="Stock keeping unit.")
    name = graphene.String(description="Variant name.", required=False)
    track_inventory = graphene.Boolean(
        description=(
            "Determines if the inventory of this variant should be tracked. If false, "
            "the quantity won't change when customers buy this item."
        )
    )
    weight = WeightScalar(description="Weight of the Product Variant.", required=False)
    preorder = PreorderSettingsInput(
        description=(
            "Determines if variant is in preorder." + ADDED_IN_31 + PREVIEW_FEATURE
        )
    )
    quantity_limit_per_customer = graphene.Int(
        required=False,
        description=(
            "Determines maximum quantity of `ProductVariant`,"
            "that can be bought in a single checkout." + ADDED_IN_31 + PREVIEW_FEATURE
        ),
    )
    metadata = NonNullList(
        MetadataInput,
        description=(
            "Fields required to update the product variant metadata." + ADDED_IN_38
        ),
        required=False,
    )
    private_metadata = NonNullList(
        MetadataInput,
        description=(
            "Fields required to update the product variant private metadata."
            + ADDED_IN_38
        ),
        required=False,
    )
    external_reference = graphene.String(
        description="External ID of this product variant." + ADDED_IN_310,
        required=False,
    )


class ProductVariantCreateInput(ProductVariantInput):
    attributes = NonNullList(
        