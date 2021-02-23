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
    settings,
    channel_USD,
):
    """Create checkout object using GraphQL API."""
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": user_api_client.user.email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = user_api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    get_graphql_content(response)

    assert mocked_webhook_trigger.called


def test_checkout_create_with_default_channel(
    api_client, stock, graphql_address_data, channel_USD
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    quantity = 1
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": quantity, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    with warnings.catch_warnings(record=True) as warns:
        response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
        get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    lines, _ = fetch_checkout_lines(new_checkout)
    assert new_checkout.channel == channel_USD
    assert calculate_checkout_quantity(lines) == quantity

    assert any(
        [str(warning.message) == DEPRECATION_WARNING_MESSAGE for warning in warns]
    )


def test_checkout_create_with_variant_without_sku(
    api_client, stock, graphql_address_data, channel_USD
):
    variant = stock.product_variant
    variant.sku = None
    variant.save()
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    quantity = 1
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": quantity, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    lines, _ = fetch_checkout_lines(new_checkout)
    assert new_checkout.channel == channel_USD
    assert calculate_checkout_quantity(lines) == quantity
    assert lines[0].variant.sku is None


def test_checkout_create_with_inactive_channel(
    api_client, stock, graphql_address_data, channel_USD
):
    channel = channel_USD
    channel.is_active = False
    channel.save()

    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "channel"
    assert error["code"] == CheckoutErrorCode.CHANNEL_INACTIVE.name


def test_checkout_create_with_zero_quantity(
    api_client, stock, graphql_address_data, channel_USD
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 0, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "quantity"
    assert error["code"] == CheckoutErrorCode.ZERO_QUANTITY.name


def test_checkout_create_with_unavailable_variant(
    api_client, stock, graphql_address_data, channel_USD
):
    variant = stock.product_variant
    variant.channel_listings.filter(channel=channel_USD).update(price_amount=None)
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "lines"
    assert error["code"] == CheckoutErrorCode.UNAVAILABLE_VARIANT_IN_CHANNEL.name
    assert error["variants"] == [variant_id]


def test_checkout_create_with_malicious_variant_id(
    api_client, stock, graphql_address_data, channel_USD
):
    variant = stock.product_variant
    variant.channel_listings.filter(channel=channel_USD).update(price_amount=None)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variant_id = (
        "UHJvZHVjdFZhcmlhbnQ6NDkxMyd8fERCTVNfUElQRS5SRUNFSVZFX01FU1N"
        "BR0UoQ0hSKDk4KXx8Q0hSKDk4KXx8Q0hSKDk4KSwxNSl8fCc="
    )
    # This string translates to
    # ProductVariant:4913'||DBMS_PIPE.RECEIVE_MESSAGE(CHR(98)||CHR(98)||CHR(98),15)||'

    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "variantId"
    assert error["code"] == "GRAPHQL_ERROR"


def test_checkout_create_with_inactive_default_channel(
    api_client, stock, graphql_address_data, channel_USD
):
    channel_USD.is_active = False
    channel_USD.save()

    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    assert not Checkout.objects.exists()
    with warnings.catch_warnings(record=True) as warns:
        response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
        get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()

    assert new_checkout.channel == channel_USD

    assert any(
        [str(warning.message) == DEPRECATION_WARNING_MESSAGE for warning in warns]
    )


def test_checkout_create_with_inactive_and_active_default_channel(
    api_client, stock, graphql_address_data, channel_USD, channel_PLN
):
    channel_PLN.is_active = False
    channel_PLN.save()

    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    assert not Checkout.objects.exists()
    with warnings.catch_warnings(record=True) as warns:
        response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
        get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()

    assert new_checkout.channel == channel_USD

    assert any(
        [str(warning.message) == DEPRECATION_WARNING_MESSAGE for warning in warns]
    )


def test_checkout_create_with_inactive_and_two_active_default_channel(
    api_client, stock, graphql_address_data, channel_USD, channel_PLN, other_channel_USD
):
    channel_USD.is_active = False
    channel_USD.save()

    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "channel"
    assert error["code"] == CheckoutErrorCode.MISSING_CHANNEL_SLUG.name


def test_checkout_create_with_many_active_default_channel(
    api_client, stock, graphql_address_data, channel_USD, channel_PLN
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "channel"
    assert error["code"] == CheckoutErrorCode.MISSING_CHANNEL_SLUG.name


def test_checkout_create_with_many_inactive_default_channel(
    api_client, stock, graphql_address_data, channel_USD, channel_PLN
):
    channel_USD.is_active = False
    channel_USD.save()
    channel_PLN.is_active = False
    channel_PLN.save()
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "channel"
    assert error["code"] == CheckoutErrorCode.MISSING_CHANNEL_SLUG.name


def test_checkout_create_with_multiple_channel_without_channel_slug(
    api_client, stock, graphql_address_data, channel_USD, channel_PLN
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "channel"
    assert error["code"] == CheckoutErrorCode.MISSING_CHANNEL_SLUG.name


def test_checkout_create_with_multiple_channel_with_channel_slug(
    api_client, stock, graphql_address_data, channel_USD, channel_PLN
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    assert new_checkout.channel == channel_USD
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1


def test_checkout_create_with_existing_checkout_in_other_channel(
    user_api_client, stock, graphql_address_data, channel_USD, user_checkout_PLN
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    old_checkout = Checkout.objects.first()

    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }

    response = user_api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    content = get_graphql_content(response)["data"]["checkoutCreate"]

    checkout_data = content["checkout"]
    assert checkout_data["token"] != str(old_checkout.token)


def test_checkout_create_with_inactive_channel_slug(
    api_client, stock, graphql_address_data, channel_USD
):
    channel = channel_USD
    channel.is_active = False
    channel.save()
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    error = get_graphql_content(response)["data"]["checkoutCreate"]["errors"][0]

    assert error["field"] == "channel"
    assert error["code"] == CheckoutErrorCode.CHANNEL_INACTIVE.name


def test_checkout_create(api_client, stock, graphql_address_data, channel_USD):
    """Create checkout object using GraphQL API."""
  