
from unittest.mock import MagicMock, patch

import graphene
import pytest
from django.core.files import File
from django.utils import timezone
from prices import Money, TaxedMoney

from ....attribute.models import AttributeValue
from ....attribute.utils import associate_attribute_values_to_instance
from ....checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from ....checkout.utils import add_variant_to_checkout, calculate_checkout_quantity
from ....order import OrderEvents, OrderStatus
from ....order.models import OrderEvent, OrderLine
from ....plugins.manager import get_plugins_manager
from ....product import ProductTypeKind
from ....product.error_codes import ProductErrorCode
from ....product.models import (
    Category,
    Collection,
    Product,
    ProductChannelListing,
    ProductMedia,
    ProductType,
    ProductVariant,
    ProductVariantChannelListing,
    VariantMedia,
)
from ....tests.utils import flush_post_commit_hooks
from ....thumbnail.models import Thumbnail
from ...tests.utils import get_graphql_content


@pytest.fixture
def category_list():
    category_1 = Category.objects.create(name="Category 1", slug="category-1")
    category_2 = Category.objects.create(name="Category 2", slug="category-2")
    category_3 = Category.objects.create(name="Category 3", slug="category-3")
    return category_1, category_2, category_3


@pytest.fixture
def product_type_list():
    product_type_1 = ProductType.objects.create(
        name="Type 1", slug="type-1", kind=ProductTypeKind.NORMAL
    )
    product_type_2 = ProductType.objects.create(
        name="Type 2", slug="type-2", kind=ProductTypeKind.NORMAL
    )
    product_type_3 = ProductType.objects.create(
        name="Type 3", slug="type-3", kind=ProductTypeKind.NORMAL
    )
    return product_type_1, product_type_2, product_type_3


MUTATION_CATEGORY_BULK_DELETE = """
    mutation categoryBulkDelete($ids: [ID!]!) {
        categoryBulkDelete(ids: $ids) {
            count
        }
    }
"""


def test_delete_categories(staff_api_client, category_list, permission_manage_products):
    variables = {
        "ids": [
            graphene.Node.to_global_id("Category", category.id)
            for category in category_list
        ]
    }
    response = staff_api_client.post_graphql(
        MUTATION_CATEGORY_BULK_DELETE,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)

    assert content["data"]["categoryBulkDelete"]["count"] == 3
    assert not Category.objects.filter(
        id__in=[category.id for category in category_list]
    ).exists()


@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_delete_categories_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_api_client,
    category_list,
    permission_manage_products,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    variables = {
        "ids": [
            graphene.Node.to_global_id("Category", category.id)
            for category in category_list
        ]
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_CATEGORY_BULK_DELETE,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)

    # then
    assert content["data"]["categoryBulkDelete"]["count"] == 3
    assert mocked_webhook_trigger.call_count == len(category_list)


def test_delete_categories_with_images(
    staff_api_client,
    category_list,
    image_list,
    permission_manage_products,
    media_root,
):
    category_list[0].background_image = image_list[0]
    category_list[0].save(update_fields=["background_image"])

    category_list[1].background_image = image_list[1]
    category_list[1].save(update_fields=["background_image"])

    thumbnail_mock = MagicMock(spec=File)
    thumbnail_mock.name = "thumbnail_image.jpg"
    Thumbnail.objects.bulk_create(
        [
            Thumbnail(category=category_list[0], size=128, image=thumbnail_mock),
            Thumbnail(category=category_list[1], size=128, image=thumbnail_mock),
        ]
    )

    variables = {
        "ids": [
            graphene.Node.to_global_id("Category", category.id)
            for category in category_list
        ]
    }
    response = staff_api_client.post_graphql(
        MUTATION_CATEGORY_BULK_DELETE,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)

    assert content["data"]["categoryBulkDelete"]["count"] == 3
    assert not Category.objects.filter(
        id__in=[category.id for category in category_list]
    ).exists()
    # ensure corresponding thumbnails has been deleted
    assert not Thumbnail.objects.all()


@patch("saleor.plugins.manager.PluginsManager.product_updated")
def test_delete_categories_trigger_product_updated_webhook(
    product_updated_mock,
    staff_api_client,
    category_list,
    product_list,
    permission_manage_products,
):
    first_product = product_list[0]
    first_product.category = category_list[0]
    first_product.save()

    second_product = product_list[1]
    second_product.category = category_list[1]
    second_product.save()

    variables = {
        "ids": [
            graphene.Node.to_global_id("Category", category.id)
            for category in category_list
        ]
    }
    response = staff_api_client.post_graphql(
        MUTATION_CATEGORY_BULK_DELETE,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)

    assert content["data"]["categoryBulkDelete"]["count"] == 3
    assert not Category.objects.filter(
        id__in=[category.id for category in category_list]
    ).exists()

    # updated two categories with products
    assert product_updated_mock.call_count == 2


@patch("saleor.product.utils.update_products_discounted_prices_task")
def test_delete_categories_with_subcategories_and_products(
    mock_update_products_discounted_prices_task,
    staff_api_client,
    category_list,
    permission_manage_products,
    product,
    category,
    channel_USD,
    channel_PLN,
):
    product.category = category
    category.parent = category_list[0]
    category.save()

    parent_product = Product.objects.get(pk=product.pk)
    parent_product.slug = "parent-product"
    parent_product.id = None
    parent_product.category = category_list[0]
    parent_product.save()

    ProductChannelListing.objects.bulk_create(
        [
            ProductChannelListing(
                product=parent_product, channel=channel_USD, is_published=True
            ),
            ProductChannelListing(
                product=parent_product,
                channel=channel_PLN,
                is_published=True,
                published_at=timezone.now(),
            ),
        ]
    )

    product_list = [product, parent_product]

    variables = {
        "ids": [
            graphene.Node.to_global_id("Category", category.id)
            for category in category_list
        ]
    }
    response = staff_api_client.post_graphql(
        MUTATION_CATEGORY_BULK_DELETE,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)

    assert content["data"]["categoryBulkDelete"]["count"] == 3
    assert not Category.objects.filter(
        id__in=[category.id for category in category_list]
    ).exists()

    mock_update_products_discounted_prices_task.delay.assert_called_once()
    (
        _call_args,
        call_kwargs,
    ) = mock_update_products_discounted_prices_task.delay.call_args

    assert set(call_kwargs["product_ids"]) == set([p.pk for p in product_list])

    for product in product_list:
        product.refresh_from_db()
        assert not product.category

    product_channel_listings = ProductChannelListing.objects.filter(
        product__in=product_list
    )
    for product_channel_listing in product_channel_listings:
        assert product_channel_listing.is_published is False
        assert not product_channel_listing.published_at
    assert product_channel_listings.count() == 3


MUTATION_COLLECTION_BULK_DELETE = """
    mutation collectionBulkDelete($ids: [ID!]!) {
        collectionBulkDelete(ids: $ids) {
            count
        }
    }
"""


def test_delete_collections(
    staff_api_client, collection_list, permission_manage_products
):
    query = MUTATION_COLLECTION_BULK_DELETE

    variables = {
        "ids": [
            graphene.Node.to_global_id("Collection", collection.id)
            for collection in collection_list
        ]
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)

    assert content["data"]["collectionBulkDelete"]["count"] == 3
    assert not Collection.objects.filter(
        id__in=[collection.id for collection in collection_list]
    ).exists()


def test_delete_collections_with_images(
    staff_api_client,
    collection_list,
    image_list,
    permission_manage_products,
    media_root,
):
    query = MUTATION_COLLECTION_BULK_DELETE

    collection_list[0].background_image = image_list[0]
    collection_list[0].save(update_fields=["background_image"])

    collection_list[1].background_image = image_list[1]
    collection_list[1].save(update_fields=["background_image"])

    thumbnail_mock = MagicMock(spec=File)
    thumbnail_mock.name = "thumbnail_image.jpg"
    Thumbnail.objects.bulk_create(
        [
            Thumbnail(collection=collection_list[0], size=128, image=thumbnail_mock),
            Thumbnail(collection=collection_list[1], size=128, image=thumbnail_mock),
        ]
    )

    variables = {
        "ids": [
            graphene.Node.to_global_id("Collection", collection.id)
            for collection in collection_list
        ]
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)

    assert content["data"]["collectionBulkDelete"]["count"] == 3
    assert not Collection.objects.filter(
        id__in=[collection.id for collection in collection_list]
    ).exists()
    # ensure corresponding thumbnails has been deleted
    assert not Thumbnail.objects.all()


@patch("saleor.plugins.manager.PluginsManager.collection_deleted")
def test_delete_collections_trigger_collection_deleted_webhook(
    collection_deleted_mock,
    staff_api_client,
    collection_list,
    permission_manage_products,
):
    variables = {
        "ids": [
            graphene.Node.to_global_id("Collection", collection.id)
            for collection in collection_list
        ]
    }
    response = staff_api_client.post_graphql(
        MUTATION_COLLECTION_BULK_DELETE,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)

    assert content["data"]["collectionBulkDelete"]["count"] == 3
    assert not Collection.objects.filter(
        id__in=[collection.id for collection in collection_list]
    ).exists()
    assert len(collection_list) == collection_deleted_mock.call_count


@patch("saleor.plugins.manager.PluginsManager.product_updated")
def test_delete_collections_trigger_product_updated_webhook(
    product_updated_mock,
    staff_api_client,
    collection_list,
    product_list,
    permission_manage_products,
):
    for collection in collection_list:
        collection.products.add(*product_list)
    variables = {
        "ids": [
            graphene.Node.to_global_id("Collection", collection.id)
            for collection in collection_list
        ]
    }
    response = staff_api_client.post_graphql(
        MUTATION_COLLECTION_BULK_DELETE,
        variables,