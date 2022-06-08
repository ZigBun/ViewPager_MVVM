import graphene

from .....app.models import App
from .....webhook.models import Webhook
from ....tests.utils import (
    assert_no_permission,
    get_graphql_content,
    get_graphql_content_from_response,
)
from ...enums import WebhookEventTypeAsyncEnum, WebhookEventTypeSyncEnum

QUERY_WEBHOOK = """
    query webhook($id: ID!) {
      webhook(id: $id) {
        id
        isActive
        subscriptionQuery
        asyncEvents {
          eventType
        }
        syncEvents {
          eventType
        }
      }
    }
"""


def test_query_webhook_by_staff(staff_api_client, webhook, permission_manage_apps):
    query = QUERY_WEBHOOK

    webhook_id = graphene.Node.to_global_id("Webhook", webhook.pk)
    variables = {"id": webhook_id}
    staff_api_client.user.user_permissions.add(permission_manage_apps)
    response = staff_api_client.post_graphql(query, variables=variables)

    content = get_graphql_content(response)
    webhook_response = content["data"]["webhook"]
    assert webhook_response["id"] == webhook_id
    assert webhook_response["isActive"] == webhook.is_active
    assert webhook_response["subscriptionQuery"] is None
    events = webhook.events.all()
    assert len(events) == 1
    assert events[0].event_type == WebhookEventTypeAsyncEnum.ORDER_CREATED.value


def test_query_webhook_with_subscription_query_by_staff(
    staff_api_client, subscription_order_created_webhook, permission_manage_apps
):
    query = QUERY_WEBHOOK
    webhook = subscription_order_created_webhook
    webhook_id = graphene.Node.to_global_id("Webhook", webhook.pk)
    variables = {"id": webhook_id}
    sta