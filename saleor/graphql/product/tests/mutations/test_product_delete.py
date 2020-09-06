from unittest.mock import patch

import graphene
import pytest
from django.utils.functional import SimpleLazyObject
from freezegun import freeze_time
from prices import Money, TaxedMoney

from .....attribute.models import AttributeValue
from .....attribute.utils import associate_attribute_values_to_instance
from .....graphql.tests.utils import get_graphql_content
from .....order import OrderEvents, OrderStatus
from .....order.models import OrderEvent, OrderLine
from .....webhook.event_types import WebhookEventAsyncType
from .....webhook.payloads import generate_product_deleted_payload

DELETE_PRODUCT_MUTATION = """
    mutation DeleteProduct($id: ID!) {
        productDelete(id: $id) {
            product {
                name
                id
                attributes {
                    values {
                        value
                        name
                    }
                }
            }
            errors {
                field
                message
            }
            }
        }
"""


@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_product(
    mocked_recalculate_orders_task,
    staff_api_client,
    product,
    permission_manage_products,
):
    query = DELETE_PRODUCT_MUTATION
    node_id = graphene.Node.to_global_id("Product", product.id)
    variables = {"id": node_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)
    data = content["data"]["productDelete"]
    assert data["product"]["name"] == product.name
    with pytest.raises(product._meta.model.DoesNotExist):
        product.refresh_from_db()
    assert node_id == data["product"]["id"]
    mocked_recalculate_orders_task.assert_not_called()


@patch("saleor.product.signals.delete_from_storage_task.delay")
@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_product_with_image(
    mocked_recalculate_orders_task,
    delete_from_storage_task_mock,
    staff_api_client,
    product_with_image,
    variant_with_image,
    permission_manage_products,
    media_root,
):
    """Ensure deleting product delete also product and variants images from storage."""

    # given
    query = DELETE_PRODUCT_MUTATION
    product = product_with_image
    variant = product.variants.first()
    node_id = graphene.Node.to_global_id("Product", product.id)

    product_img_paths = [media.image for media in product.media.all()]
    variant_img_paths = [media.image for media in variant.media.all()]
    product_media_paths = [media.image.name for media in product.media.all()]
    variant_media_paths = [media.image.name for media in variant.media.all()]
    images = product_img_paths + variant_img_paths

    variables = {"id": node_id}

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["productDelete"]
    assert data["product"]["name"] == product.name
    with pytest.raises(product._meta.model.DoesNotExist):
        product.refresh_from_db()
    assert node_id == data["product"]["id"]

    assert delete_from_storage_task_mock.call_count == len(images)
    assert {
        call_args.args[0] for call_args in delete_from_storage_task_mock.call_args_list
    } == set(product_media_paths + variant_media_paths)
    mocked_recalculate_orders_task.assert_not_called()


@freeze_time("1914-06-28 10:50")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_product_trigger_webhook(
    mocked_recalculate_orders_task,
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_api_client,
    product,
    permission_manage_products,
    settings,
):
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    query = DELETE_PRODUCT_MUTATION
    node_id = graphene.Node.to_global_id("Product", product.id)
    variants_id = list(product.variants.all().values_list("id", flat=True))
    variables = {"id": node_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)
    data = content["data"]["productDelete"]
    assert data["product"]["name"] == product.name
    with pytest.raises(product._meta.model.DoesNotExist):
        product.refresh_from_db()
    assert node_id == data["product"]["id"]
    expected_data = generate_product_deleted_payload(
        product, variants_id, staff_api_client.user
    )
    mocked_webhook_trigger.assert_called_once_with(
        expected_data,
        WebhookEventAsyncType.PRODUCT_DELETED,
        [any_webhook],
        product,
        SimpleLazyObject(lambda: staff_api_client.user),
    )
    mocked_recalculate_orders_task.assert_not_called()


@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_product_with_file_attribute(
    mocked_recalculate_orders_task,
    staff_api_client,
    product,
    permission_manage_products,
    file_attribute,
):
    query = DELETE_PRODUCT_MUTATION
    product_type = product.product_type
    product_type.product_attributes.add(file_attribute)
    existing_value = file_attribute.values.first()
    associate_attribute_values_to_instance(product, file_attribute, existing_value)

    node_id = graphene.Node.to_global_id("Product", product.id)
    variables = {"id": node_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)
    data = content["data"]["productDelete"]
    assert data["product"]["name"] == product.name
    with pytest.raises(product._meta.model.DoesNotExist):
        product.refresh_from_db()
    assert node_id == data["product"]["id"]
    mocked_recalculate_orders_task.assert_not_called()
    with pytest.raises(existing_value._meta.model.DoesNotExist):
        existing_value.refresh_from_db()


def test_delete_product_removes_checkout_lines(
    staff_api_client,
    checkout_with_items,
    permission_manage_products,
    settings,
):
    query = DELETE_PRODUCT_MUTATION
    checkout = checkout_with_items
    line = checkout.lines.first()
    product = line.variant.product
    node_id = graphene.Node.to_global_id("Product", product.id)
    variables = {"id": node_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_products]
    )
    content = get_graphql_content(response)
    data = content["data"]["productDelete"]
    assert data["product"]["name"] == product.name

    with pytest.raises(product._meta.model.DoesNotExist):
        product.refresh_from_db()

    with pytest.raises(line._meta.model.DoesNotExist):
        line.refresh_from_db()
    assert checkout.lines.all().exists()

    checkout.refresh_from_db()

    assert node_id == data["product"]["id"]


@patch("saleor.order.tasks.recalculate_orders_task.delay")
def test_delete_product_variant_in_draft_order(
    mocked_recalculate_orders_task,
    staff_api_client,
    product_with_two_variants,
    permission_manage_products,
    order_list,
    channel_USD,
):
    query = DELETE_PRODUCT_MUTATION
    product = product_with_two_variants

    not_draft_order = order_list[1]
    draft_order = order_list[0]
    draft_order.status = OrderStatus.DRAFT
    draft_order.save(update_fields=["status"])

    draft_order_lines_pks = []
    not_draft_order_lines_pks = []
    for variant in product.variants.all():
        variant_channel_listing = variant.channel_listings.get(channel=channel_USD)
        net = variant.get_price(product, [], channel_USD, variant_channel_listing, None)
        gross = Money(amount=net.amount, currency=net.currency)
        unit_price = TaxedMoney(net=net, gross=gross)
        quantity = 3
        total_price = unit_price * quantity

        order_line = OrderLine.objects.create