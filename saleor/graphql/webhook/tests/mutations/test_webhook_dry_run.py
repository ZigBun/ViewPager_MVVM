
import json
import uuid

import graphene
import pytest

from .....graphql.tests.utils import get_graphql_content
from .....webhook.error_codes import WebhookDryRunErrorCode
from .....webhook.event_types import WebhookEventAsyncType
from ....tests.utils import assert_no_permission
from ...subscription_types import WEBHOOK_TYPES_MAP

WEBHOOK_DRY_RUN_MUTATION = """
    mutation webhookDryRun($query: String!, $objectId: ID!) {
        webhookDryRun(query: $query, objectId: $objectId) {
            errors {
                field
                code
                message
            }
            payload
        }
    }
    """


def test_webhook_dry_run(
    staff_api_client,
    permission_manage_orders,
    order,
    subscription_order_created_webhook,
):
    # given
    query = WEBHOOK_DRY_RUN_MUTATION
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    order_id = graphene.Node.to_global_id("Order", order.id)
    webhook = subscription_order_created_webhook

    variables = {"objectId": order_id, "query": webhook.subscription_query}

    # when
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)

    # then
    data = content["data"]["webhookDryRun"]
    payload = json.loads(data["payload"])
    assert payload["order"]["id"] == order_id


def test_webhook_dry_run_missing_user_permission(
    staff_api_client,
    order,
    subscription_order_created_webhook,
):
    # given
    query = WEBHOOK_DRY_RUN_MUTATION
    order_id = graphene.Node.to_global_id("Order", order.id)
    webhook = subscription_order_created_webhook

    variables = {"objectId": order_id, "query": webhook.subscription_query}

    # when
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)

    # then
    error = content["data"]["webhookDryRun"]["errors"][0]
    assert not error["field"]
    assert error["code"] == WebhookDryRunErrorCode.MISSING_PERMISSION.name
    assert (
        error["message"] == "The user doesn't have required permission: manage_orders."
    )


def test_webhook_dry_run_staff_user_not_authorized(
    user_api_client,
    permission_manage_orders,
    order,
    subscription_order_created_webhook,
):
    # given
    query = WEBHOOK_DRY_RUN_MUTATION
    user_api_client.user.user_permissions.add(permission_manage_orders)
    order_id = graphene.Node.to_global_id("Order", order.id)
    webhook = subscription_order_created_webhook

    variables = {"objectId": order_id, "query": webhook.subscription_query}

    # when
    response = user_api_client.post_graphql(query, variables)

    # then
    assert_no_permission(response)


def test_webhook_dry_run_non_existing_id(
    staff_api_client,
    permission_manage_orders,
    order,
    subscription_order_created_webhook,
):
    # given
    query = WEBHOOK_DRY_RUN_MUTATION
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    order_id = graphene.Node.to_global_id("Order", uuid.uuid4())
    webhook = subscription_order_created_webhook

    variables = {"objectId": order_id, "query": webhook.subscription_query}

    # when
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)

    # then
    error = content["data"]["webhookDryRun"]["errors"][0]
    assert error["field"] == "objectId"
    assert error["code"] == WebhookDryRunErrorCode.NOT_FOUND.name
    assert error["message"] == f"Couldn't resolve to a node: {order_id}"


def test_webhook_dry_run_invalid_query(
    staff_api_client,
    permission_manage_orders,
    order,
    subscription_order_created_webhook,
):
    # given
    query = WEBHOOK_DRY_RUN_MUTATION
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    order_id = graphene.Node.to_global_id("Order", order.id)
    webhook = subscription_order_created_webhook
    subscription = webhook.subscription_query.replace("OrderCreated", "UndefinedEvent")

    variables = {"objectId": order_id, "query": subscription}

    # when
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)

    # then
    error = content["data"]["webhookDryRun"]["errors"][0]
    assert error["field"] == "query"
    assert error["code"] == WebhookDryRunErrorCode.GRAPHQL_ERROR.name
    assert 'Unknown type "UndefinedEvent"' in error["message"]


def test_webhook_dry_run_object_id_does_not_match_event(
    staff_api_client,
    permission_manage_orders,
    product,
    subscription_order_created_webhook,
):
    # given
    query = WEBHOOK_DRY_RUN_MUTATION
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    product_id = graphene.Node.to_global_id("Product", product.id)
    webhook = subscription_order_created_webhook

    variables = {"objectId": product_id, "query": webhook.subscription_query}

    # when
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)

    # then
    error = content["data"]["webhookDryRun"]["errors"][0]
    assert error["field"] == "objectId"
    assert error["code"] == WebhookDryRunErrorCode.INVALID_ID.name
    assert error["message"] == "ObjectId doesn't match event type."


def test_webhook_dry_run_event_type_not_supported(
    staff_api_client,
    permission_manage_orders,
    product,
    subscription_payment_authorize_webhook,
):
    # given
    query = WEBHOOK_DRY_RUN_MUTATION
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    product_id = graphene.Node.to_global_id("Product", product.id)
    webhook = subscription_payment_authorize_webhook

    variables = {"objectId": product_id, "query": webhook.subscription_query}

    # when
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)

    # then
    error = content["data"]["webhookDryRun"]["errors"][0]
    assert error["field"] == "query"
    assert error["code"] == WebhookDryRunErrorCode.TYPE_NOT_SUPPORTED.name
    assert error["message"] == "Event type: PaymentAuthorize not supported."


@pytest.fixture
def async_subscription_webhooks_with_root_objects(
    subscription_address_created_webhook,
    subscription_address_updated_webhook,
    subscription_address_deleted_webhook,
    subscription_app_installed_webhook,
    subscription_app_updated_webhook,
    subscription_app_deleted_webhook,