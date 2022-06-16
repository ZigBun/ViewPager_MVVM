from django.db import models

from ...core.models import SortableModel
from ...product.models import ProductType, ProductVariant
from .base import AssociatedAttributeManager, BaseAssignedAttribute


class AssignedVariantAttributeValue(SortableModel):
    value = models.ForeignKey(
        "AttributeValue",
        on_delete=models.CASCADE,
        related_name="variantvalueassignment",
    )
    assignment = models.ForeignKey(
        "AssignedVariantAttribute",
        on_delete=models.CASCADE,
        related_name="variantvalueassignment",
    )

    class Meta:
        unique_together = (("value", "assignment"),)
        ordering = ("sort_order", "pk")

    def get_ordering_queryset(self):
        return self.assignment.variantvalueassignment.all()


class AssignedVariantAttribute(BaseAssignedAttribute):
    """Associate a product type attribute and selected values to a given variant."""

    variant = models.ForeignKey(
        ProductVariant, related_name="attributes", on_delete=models.CASCADE
 