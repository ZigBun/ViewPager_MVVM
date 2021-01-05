import graphene

from ..core.descriptions import ADDED_IN_38, DEPRECATED_IN_3X_INPUT
from ..core.types import SortInputObjectType


class PageSortField(graphene.Enum):
    TITLE = ["title", "slug"]
    SLUG = ["slug"]
    VISIBILITY = ["is_published", "title", "slug"]
    CREATION_DATE = ["created_at", "title", "slug"]
    PUBLICATION_DATE = ["published_at", "title", "slug"]
    PUBLISHED_AT = ["published_at", "title", "slug"]
    CREATED_AT = ["created_at", "title", "slug"]

    @property
    def description(self):
        if self.name in PageSortField.__enum__._member_names_:
            sort_name = self.name.lower().replace("_", " ")
           