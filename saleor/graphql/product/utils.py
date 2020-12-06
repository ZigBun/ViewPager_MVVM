from collections import defaultdict, namedtuple
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional

import graphene
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.utils import IntegrityError

from ...core.tracing import traced_atomic_transaction
from ...order import OrderStatus
from ...order import models as order_models
from ...warehouse.models import Stock
from ..core.enums import ProductErrorCode

if TYPE_CHECKING:
    from ...product.models import ProductVariant
    from ...warehouse.models import Warehouse

import logging

logger = logging.getLogger(__name__)


def get_used_attribute_values_for_variant(variant):
    """Create a dict of attributes values for variant.

    Sample result is:
    {
        "attribute_1_global_id": ["ValueAttr1_1"],
        "attribute_2_global_id": ["ValueAttr2_1"]
    }
    """
    attribute_values = defaultdict(list)
    for assigned_variant_attribute in variant.attributes.all():
        attribute = assigned_variant_attribute.attribute
        attribute_id = graphene.Node.to_global_id("Attribute", attribute.id)
        for attr_value in assigned_variant_attribute.values.all():
            attribute_values[attribute_id].append(attr_value.slug)
    return attribute_values


def get_used_variants_attribute_values(product):
    """Create list of attributes values for all existing `ProductVariants` for product.

    Sample result is:
    [
        {
            "attribute_1_global_id": ["ValueAttr1_1"],
            "attribute_2_global_id": ["ValueAttr2_1"]
        },
        ...
        {
            "attribute_1_global_id": ["ValueAttr1_2"],
            "attribute_2_g