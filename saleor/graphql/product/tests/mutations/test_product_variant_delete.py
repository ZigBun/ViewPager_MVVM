from unittest.mock import patch

import graphene
import pytest
from prices import Money, TaxedMoney

from .....order import OrderEvents, OrderStatus
from .....order.models import OrderEvent, OrderLine
from .....product.models import ProductVariant
from .....tests.utils import flush_post_commit_hooks
from ....tests.utils import get_graphql_content

DELETE_VARIANT_BY_SKU_MUTATION = """
    mutation variantDelete($sku: String) {
        productVariantDelete(sku: $sku) {
            productVariant {
                sku
                id
            }
            }
        }
"""


@patch("saleor.plugins.manager.PluginsManager.product_variant_deleted")
@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_variant_by_sku(
    mocked_recalculate_orders_task,
    product_variant_deleted_webhook_mock,
    staff_api_client,
    product,
    permission_manage_products,
):
    # given
    variant = product.variants.first()
    variant_sku = variant.sku
    variables = {"sku": variant_sku}

    # when
    response = staff_api_client.post_graphql(
        DELETE_VARIANT_BY_SKU_MUTATION,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)
    flush_post_commit_hooks()
    data = content["data"]["productVariantDelete"]

    # then
    product_variant_deleted_webhook_mock.assert_called_once_with(variant)
    assert data["productVariant"]["sku"] == variant_sku
    with pytest.raises(variant._meta.model.DoesNotExist):
        variant.refresh_from_db()
    mocked_recalculate_orders_task.assert_not_called()


DELETE_VARIANT_MUTATION = """
    mutation variantDelete($id: ID!) {
        productVariantDelete(id: $id) {
            productVariant {
                sku
                id
            }
            }
        }
"""


@patch("saleor.plugins.manager.PluginsManager.product_variant_deleted")
@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_variant(
    mocked_recalculate_orders_task,
    product_variant_deleted_webhook_mock,
    staff_api_client,
    product,
    permission_manage_products,
):
    query = DELETE_VARIANT_MUTATION
    variant = product.variants.first()
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    variant_sku = variant.sku
    variables = {"id": variant_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)
    flush_post_commit_hooks()
    data = content["data"]["productVariantDelete"]

    product_variant_deleted_webhook_mock.assert_called_once_with(variant)
    assert data["productVariant"]["sku"] == variant_sku
    with pytest.raises(variant._meta.model.DoesNotExist):
        variant.refresh_from_db()
    mocked_recalculate_orders_task.assert_not_called()


def test_delete_variant_remove_checkout_lines(
    staff_api_client,
    checkout_with_items,
    permission_manage_products,
):
    query = DELETE_VARIANT_MUTATION
    line = checkout_with_items.lines.first()
    variant = line.variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    variables = {"id": variant_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)
    flush_post_commit_hooks()
    data = content["data"]["productVariantDelete"]

    assert data["productVariant"]["sku"] == variant.sku
    with pytest.raises(variant._meta.model.DoesNotExist):
        variant.refresh_from_db()
    with pytest.raises(line._meta.model.DoesNotExist):
        line.refresh_from_db()


@patch("saleor.product.signals.delete_from_storage_task.delay")
@patch("saleor.plugins.manager.PluginsManager.product_variant_deleted")
@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_variant_with_image(
    mocked_recalculate_orders_task,
    product_variant_deleted_webhook_mock,
    delete_from_storage_task_mock,
    staff_api_client,
    variant_with_image,
    permission_manage_products,
    media_root,
):
    """Ensure deleting variant doesn't delete linked product image."""

    query = DELETE_VARIANT_MUTATION
    variant = variant_with_image

    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    variables = {"id": variant_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)
    flush_post_commit_hooks()
    data = content["data"]["productVariantDelete"]

    product_variant_deleted_webhook_mock.assert_called_once_with(variant)
    assert data["productVariant"]["sku"] == variant.sku
    with pytest.raises(variant._meta.model.DoesNotExist):
        variant.refresh_from_db()
    mocked_recalculate_orders_task.assert_not_called()
    delete_from_storage_task_mock.assert_not_called()


@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_variant_in_draft_order(
    mocked_recalculate_orders_task,
    staff_api_client,
    