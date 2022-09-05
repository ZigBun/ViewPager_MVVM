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
            product_count=Coalesce(
                Subquery(
                    Category.tree.add_related_count(
                        queryset, Product, "category", "p_c", cumulative=True
                    )
                    .values("p_c")
                    .filter(pk=OuterRef("pk"))[:1]
                ),
                0,
                output_field=IntegerField(),
            )
        )

    @staticmethod
    def qs_with_subcategory_count(queryset: QuerySet, **_kwargs) -> QuerySet:
        return queryset.annotate(subcategory_count=Count("children__id"))


class CategorySortingInput(ChannelSortInputObjectType):
    class Meta:
        sort_enum = CategorySortField
        type_name = "categories"


class CollectionSortField(graphene.Enum):
    NAME = ["name", "slug"]
    AVAILABILITY = ["is_published", "slug"]
    PRODUCT_COUNT = ["product_count", "slug"]
    PUBLICATION_DATE = ["published_at", "slug"]
    PUBLISHED_AT = ["published_at", "slug"]

    @property
    def description(self):
        descrption_extras = {
            CollectionSortField.AVAILABILITY.name: [CHANNEL_REQUIRED],  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
            CollectionSortField.PUBLICATION_DATE.name: [  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                CHANNEL_REQUIRED,
                DEPRECATED_IN_3X_INPUT,
            ],
            CollectionSortField.PUBLISHED_AT.name: [CHANNEL_REQUIRED],  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
        }
        if self.name in CollectionSortField.__enum__._member_names_:
            sort_name = self.name.lower().replace("_", " ")
            description = f"Sort collections by {sort_name}."
            if extras := descrption_extras.get(self.name):
                description += "".join(extras)
            return description
        raise ValueError(f"Unsupported enum value: {self.value}")

    @staticmethod
    def qs_with_product_count(queryset: QuerySet, **_kwargs) -> QuerySet:
        return queryset.annotate(product_count=Count("collectionproduct__id"))

    @staticmethod
    def qs_with_availability(queryset: QuerySet, channel_slug: str) -> QuerySet:
        subquery = Subquery(
            CollectionChannelListing.objects.filter(
                collection_id=OuterRef("pk"), channel__slug=str(channel_slug)
            ).values_list("is_published")[:1]
        )
        return queryset.annotate(
            is_published=ExpressionWrapper(subquery, output_field=BooleanField())
        )

    @staticmethod
    def qs_with_publication_date(queryset: QuerySet, channel_slug: str) -> QuerySet:
        return CollectionSortField.qs_with_published_at(queryset, channel_slug)

    @staticmethod
    def qs_with_published_at(queryset: QuerySet, channel_slug: str) -> QuerySet:
        subquery = Subquery(
            CollectionChannelListing.objects.filter(
                collection_id=OuterRef("pk"), channel__slug=str(channel_slug)
            ).values_list("published_at")[:1]
        )
        return queryset.annotate(
            published_at=ExpressionWrapper(subquery, output_field=DateTimeField())
        )


class CollectionSortingInput(ChannelSortInputObjectType):
    class Meta:
        sort_enum = CollectionSortField
        type_name = "collections"


class ProductOrderField(graphene.Enum):
    NAME = ["name", "slug"]
    RANK = ["search_rank", "id"]
    PRICE = ["min_variants_price_amount", "name", "slug"]
    MINIMAL_PRICE = ["discounted_price_amount", "name", "slug"]
    LAST_MODIFIED = ["updated_at", "name", "slug"]
    DATE = ["updated_at", "name", "slug"]
    TYPE = ["product_type__name", "name", "slug"]
    PUBLISHED = ["is_published", "name", "slug"]
    PUBLICATION_DATE = ["published_at", "name", "slug"]
    PUBLISHED_AT = ["published_at", "name", "slug"]
    LAST_MODIFIED_AT = ["updated_at", "name", "slug"]
    COLLECTION = ["collectionproduct__sort_order", "pk"]
    RATING = ["rating", "name", "slug"]
    CREATED_AT = ["created_at", "name", "slug"]

    @property
    def description(self):
        # pylint: disable=no-member
        descriptions = {
            ProductOrderField.COLLECTION.name: (  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                "collection. Note: "
                "This option is available only for the `Collection.products` query."
                + CHANNEL_REQUIRED
            ),
            ProductOrderField.RANK.name: (  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                "rank. Note: This option is available only with the `search` filter."
            ),
            ProductOrderField.NAME.name: "name.",  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
            ProductOrderField.PRICE.name: ("price." + CHANNEL_REQUIRED),  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
            ProductOrderField.TYPE.name: "type.",  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
            ProductOrderField.MINIMAL_PRICE.name: (  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                "a minimal price of a product's variant." + CHANNEL_REQUIRED
            ),
            ProductOrderField.DATE.name: f"update date. {DEPRECATED_IN_3X_INPUT}",  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
            ProductOrderField.PUBLISHED.name: (  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                "publication status." + CHANNEL_REQUIRED
            ),
            ProductOrderField.PUBLICATION_DATE.name: (  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                "publication date." + CHANNEL_REQUIRED + DEPRECATED_IN_3X_INPUT
            ),
            ProductOrderField.LAST_MODIFIED.name: (  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                f"update date. {DEPRECATED_IN_3X_INPUT}"
            ),
            ProductOrderField.PUBLISHED_AT.name: (  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
                "publication date." + CHANNEL_REQUIRED
            ),
            ProductOrderField.LAST_MODIFIED_AT.name: "update date.",  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
            ProductOrderField.RATING.name: "rating.",  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
            ProductOrderField.CREATED_AT.name: "creation date." + ADDED_IN_38,  # type: ignore[attr-defined] # graphene.Enum is not typed # noqa: E501
        }
        if self.name in descriptions:
            return f"Sort products by {descriptions[self.name]}"
        raise ValueError(f"Unsupported enum value: {self.value}")

    @staticmethod
    def qs_with_price(queryset: QuerySet, channel_slug: str) -> QuerySet:
        return queryset.annotate(
            min_variants_price_amount=Min(
                "variants__channel_listings__price_amount",
                filter=Q(variants__channel_listings__channel__slug=str(channel_slug))
                & Q(variants__channel_listings__price_amount__isnull=False),
            )
        )

    @staticmethod
    def qs_with_minimal_price(queryset: QuerySet, channel_slug: str) -> QuerySet:
        return queryset.annotate(
            discounted_price_amount=Min(
                "channel_listings__discounted_price_amount",
                filter=Q(channel_listings__channel__slug=str(channel_slug)),
            )
        )

    @staticmethod
    def qs_with_published(queryset: QuerySet, channel_slug: str) -> QuerySe