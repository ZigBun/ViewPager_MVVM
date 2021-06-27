import dataclasses
import json
from decimal import Decimal
from unittest import mock

import graphene

from .....core.models import EventDelivery
from .....graphql.discount.enums import DiscountValueTypeEnum
from .....graphql.order.tests.mutations.test_order_discount import ORDER_DISCOUNT_ADD
from .....graphql.product.tests.mutations.test_product_create import (
    CREATE_PRODUCT_MUTATION,
)
from .....webhook.event_types import WebhookEventAsyncType, WebhookEventSyncType
from .....webhook.models import Webhook
from ...tasks import trigger_webhook_sync, trigger_webhooks_async
from .payloads import generate_payment_payload

TEST_ID = "test_id"


@dataclasses.dataclass
class FakeDelivery:
 