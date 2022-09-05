import graphene
from django.db.models import (
    BooleanField,
    Count,
    DateTimeField,
    ExpressionWrapper,
    F,
    IntegerField,
    Min,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
)
from django.db.models.expressions import Window
from django.db.models.functions import Coalesce, DenseRank

from ...product.models import (
    Category,
    CollectionChannelListing,
    Product,
    ProductChannelListing,
)
from ..core.descriptions import ADDED_IN_38, CHANNEL_REQUIRED, DEPRECATED_IN_3X_INPUT
from ..core.types import ChannelSortInputObjectType, SortInputObjectType


class CategorySortField(graphene.Enum):
    NAME = ["name", "slug"]
    PRODUCT_COUNT = ["product_count", "name", "slug"]
    SUBCATEGORY_COUNT = ["subcategory_count", "name", "slug"]

    @property
    def description(self):
        # pylint: disable=no-member
        if self in [
            CategorySortField.NAME,
            CategorySortField.PRODUCT_COUNT,
            CategorySortField.SUBCATEGORY_COUNT,
        ]:
            sort_name = self.name.lower().replace("_", " ")
            return f"Sort categories by {sort_name}."
        raise ValueError(f"Unsupported enum value: {self.value}")

    @staticmethod
    def qs_with_product_count(queryset: QuerySet, **_kwargs) -> QuerySet:
        return queryset.annotate(