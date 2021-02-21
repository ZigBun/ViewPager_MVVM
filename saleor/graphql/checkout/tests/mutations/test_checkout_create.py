import datetime
import warnings
from unittest import mock

import graphene
import pytest
import pytz
from django.test import override_settings
from django.utils import timezone

from .....account.models import Address
from .....channel.utils import DEPRECATION_WARNING_MESSAGE
from .....checkout import AddressType
from .....checkout.error_codes import CheckoutErrorCode
from .....checkout.fetch import fetch_checkout_lines
from .....checkout.models import Checkout
from .....checkout.utils import calculate_checkout_quantity
from .....product.models import ProductChannelListing
from .....warehouse.models import Reservation, Stock
from ....tests.utils import assert_no_permission, get_graphql_content

MUTATION_CHECKOUT_CREATE = """
    mutation createCheckout($checkoutInput: CheckoutCreateInput!) {
      checkoutCreate(input: $checkoutInput) {
        checkout {
          id
          token
          email
          quantity
          lines {
            quantity
          }
        }
        errors {
          field
          message
          code
          variants
          addressType
        }
      }
    }
"""


@mock.patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@mock.patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_checkout_create_triggers_webhooks(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    user_api_client,
    stock,
    graphql_address_data,
    