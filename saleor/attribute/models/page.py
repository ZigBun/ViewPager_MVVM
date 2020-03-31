from django.db import models

from ...core.models import SortableModel
from ...page.models import Page, PageType
from .base import AssociatedAttributeManager, BaseAssignedAttribute


class AssignedPageAttributeValue(SortableModel):
    value = models.ForeignKey(
        "AttributeValue",
        on_delete=models.CASC