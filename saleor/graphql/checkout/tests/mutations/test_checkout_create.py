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
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1
    assert new_checkout.shipping_address is not None
    assert new_checkout.shipping_address.first_name == shipping_address["firstName"]
    assert new_checkout.shipping_address.last_name == shipping_address["lastName"]
    assert (
        new_checkout.shipping_address.street_address_1
        == shipping_address["streetAddress1"]
    )
    assert (
        new_checkout.shipping_address.street_address_2
        == shipping_address["streetAddress2"]
    )
    assert new_checkout.shipping_address.postal_code == shipping_address["postalCode"]
    assert new_checkout.shipping_address.country == shipping_address["country"]
    assert new_checkout.shipping_address.city == shipping_address["city"].upper()
    assert not Reservation.objects.exists()


def test_checkout_create_with_custom_price(
    app_api_client,
    stock,
    graphql_address_data,
    channel_USD,
    permission_handle_checkouts,
):
    """Ensure that app with handle checkouts permission can set custom price."""
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    price = 12.25
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id, "price": price}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = app_api_client.post_graphql(
        MUTATION_CHECKOUT_CREATE, variables, permissions=[permission_handle_checkouts]
    )
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1
    assert checkout_line.price_override == price


def test_checkout_create_with_metadata_in_line(
    api_client, stock, graphql_address_data, channel_USD
):
    """Ensure that app with handle checkouts permission can set custom price."""
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    metadata_key = "md key"
    metadata_value = "md value"
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [
                {
                    "quantity": 1,
                    "variantId": variant_id,
                    "metadata": [{"key": metadata_key, "value": metadata_value}],
                }
            ],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1
    assert checkout_line.metadata == {metadata_key: metadata_value}


def test_checkout_create_with_custom_price_duplicated_items(
    app_api_client,
    stock,
    graphql_address_data,
    channel_USD,
    permission_handle_checkouts,
):
    """Ensure that when the same item with a custom price is provided multiple times,
    the price from the last occurrence will be set."""
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    price_1 = 12.25
    price_2 = 20.25
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [
                {"quantity": 1, "variantId": variant_id, "price": price_1},
                {"quantity": 1, "variantId": variant_id, "price": price_2},
            ],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = app_api_client.post_graphql(
        MUTATION_CHECKOUT_CREATE, variables, permissions=[permission_handle_checkouts]
    )
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 2
    assert checkout_line.price_override == price_2


def test_checkout_create_with_force_new_line(
    app_api_client,
    stock,
    graphql_address_data,
    channel_USD,
    permission_handle_checkouts,
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data

    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [
                {"quantity": 1, "variantId": variant_id},
                {"quantity": 1, "variantId": variant_id, "forceNewLine": True},
            ],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = app_api_client.post_graphql(
        MUTATION_CHECKOUT_CREATE,
        variables,
        permissions=[permission_handle_checkouts],
        check_no_permissions=False,
    )
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    new_checkout_lines = new_checkout.lines.all()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert len(new_checkout_lines) == 2

    for line in new_checkout_lines:
        assert line.variant == variant
        assert line.quantity == 1


def test_checkout_create_with_custom_price_by_app_no_perm(
    app_api_client, stock, graphql_address_data, channel_USD
):
    """Ensure that app without handle checkouts permission cannot set custom price."""
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    price = 12.25
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id, "price": price}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = app_api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    assert_no_permission(response)


def test_checkout_create_with_custom_price_by_staff_with_handle_checkouts(
    staff_api_client,
    stock,
    graphql_address_data,
    channel_USD,
    permission_handle_checkouts,
):
    """Ensure that staff with handle checkouts permission cannot set custom price."""
    staff_api_client.user.user_permissions.add(permission_handle_checkouts)
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    price = 12.25
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id, "price": price}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = staff_api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    assert_no_permission(response)


def test_checkout_create_no_email(api_client, stock, graphql_address_data, channel_USD):
    """Create checkout object using GraphQL API."""
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1
    assert new_checkout.shipping_address is not None
    assert new_checkout.email is None
    assert new_checkout.shipping_address.first_name == shipping_address["firstName"]
    assert new_checkout.shipping_address.last_name == shipping_address["lastName"]
    assert (
        new_checkout.shipping_address.street_address_1
        == shipping_address["streetAddress1"]
    )
    assert (
        new_checkout.shipping_address.street_address_2
        == shipping_address["streetAddress2"]
    )
    assert new_checkout.shipping_address.postal_code == shipping_address["postalCode"]
    assert new_checkout.shipping_address.country == shipping_address["country"]
    assert new_checkout.shipping_address.city == shipping_address["city"].upper()


def test_checkout_create_stock_only_in_cc_warehouse(
    api_client, stock, graphql_address_data, channel_USD, warehouse_for_cc
):
    """Create checkout object using GraphQL API."""
    # given
    variant = stock.product_variant
    variant.stocks.all().delete()

    Stock.objects.create(
        warehouse=warehouse_for_cc, product_variant=variant, quantity=10
    )

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

    # when
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)

    # then
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1
    assert new_checkout.shipping_address is not None
    assert new_checkout.shipping_address.first_name == shipping_address["firstName"]
    assert new_checkout.shipping_address.last_name == shipping_address["lastName"]
    assert (
        new_checkout.shipping_address.street_address_1
        == shipping_address["streetAddress1"]
    )
    assert (
        new_checkout.shipping_address.street_address_2
        == shipping_address["streetAddress2"]
    )
    assert new_checkout.shipping_address.postal_code == shipping_address["postalCode"]
    assert new_checkout.shipping_address.country == shipping_address["country"]
    assert new_checkout.shipping_address.city == shipping_address["city"].upper()
    assert not Reservation.objects.exists()


def test_checkout_create_with_invalid_channel_slug(
    api_client, stock, graphql_address_data, channel_USD
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    invalid_slug = "invalid-slug"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": invalid_slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]
    error = content["errors"][0]

    assert error["code"] == CheckoutErrorCode.NOT_FOUND.name
    assert error["field"] == "channel"


def test_checkout_create_no_channel_shipping_zones(
    api_client, stock, graphql_address_data, channel_USD
):
    """Create checkout object using GraphQL API."""
    channel_USD.shipping_zones.clear()
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
    assert new_checkout is None
    errors = content["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == CheckoutErrorCode.INSUFFICIENT_STOCK.name
    assert errors[0]["field"] == "quantity"


def test_checkout_create_multiple_warehouse(
    api_client, variant_with_many_stocks, graphql_address_data, channel_USD
):
    variant = variant_with_many_stocks
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 4, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 4


def test_checkout_create_with_reservation(
    site_settings_with_reservations,
    api_client,
    variant_with_many_stocks,
    graphql_address_data,
    channel_USD,
):
    variant = variant_with_many_stocks
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 4, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line
    reservation = checkout_line.reservations.first()
    assert reservation
    assert reservation.checkout_line == checkout_line
    assert reservation.quantity_reserved == checkout_line.quantity
    assert reservation.reserved_until > timezone.now()


def test_checkout_create_with_null_as_addresses(api_client, stock, channel_USD):
    """Create checkout object using GraphQL API."""
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": None,
            "billingAddress": None,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1
    assert new_checkout.shipping_address is None
    assert new_checkout.billing_address is None


def test_checkout_create_with_variant_without_inventory_tracking(
    api_client, variant_without_inventory_tracking, channel_USD
):
    """Create checkout object using GraphQL API."""
    variant = variant_without_inventory_tracking
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    variables = {
        "checkoutInput": {
            "channel": channel_USD.slug,
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": None,
            "billingAddress": None,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    new_checkout = Checkout.objects.first()
    assert new_checkout is not None
    checkout_data = content["checkout"]
    assert checkout_data["token"] == str(new_checkout.token)
    assert new_checkout.lines.count() == 1
    checkout_line = new_checkout.lines.first()
    assert checkout_line.variant == variant
    assert checkout_line.quantity == 1
    assert new_checkout.shipping_address is None
    assert new_checkout.billing_address is None


@pytest.mark.parametrize(
    "quantity, expected_error_message, error_code",
    (
        (
            -1,
            "The quantity should be higher than zero.",
            CheckoutErrorCode.ZERO_QUANTITY,
        ),
        (
            51,
            "Cannot add more than 50 times this item: SKU_A.",
            CheckoutErrorCode.QUANTITY_GREATER_THAN_LIMIT,
        ),
    ),
)
def test_checkout_create_cannot_add_invalid_quantities(
    api_client,
    stock,
    graphql_address_data,
    quantity,
    channel_USD,
    expected_error_message,
    error_code,
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    test_email = "test@example.com"
    shipping_address = graphql_address_data
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": quantity, "variantId": variant_id}],
            "email": test_email,
            "shippingAddress": shipping_address,
            "channel": channel_USD.slug,
        }
    }
    assert not Checkout.objects.exists()
    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]
    assert content["errors"]
    assert content["errors"] == [
        {
            "field": "quantity",
            "message": expected_error_message,
            "code": error_code.name,
            "variants": None,
            "addressType": None,
        }
    ]


def test_checkout_create_reuse_checkout(checkout, user_api_client, stock):
    # assign user to the checkout
    checkout.user = user_api_client.user
    checkout.save()
    variant = stock.product_variant

    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "channel": checkout.channel.slug,
        },
    }
    response = user_api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = get_graphql_content(response)["data"]["checkoutCreate"]

    checkout_data = content["checkout"]
    assert checkout_data["token"] != str(checkout.token)

    assert len(checkout_data["lines"]) == 1


def test_checkout_create_required_country_shipping_address(
    api_client, stock, graphql_address_data, channel_USD
):
    variant = stock.product_variant
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.id)
    shipping_address = graphql_address_data
    del shipping_address["country"]
    variables = {
        "checkoutInput": {
            "lines": [{"quantity": 1, "variantId": variant_id}],
            "email": "test@example.com",
            "shippingAddress": shipping_address,
            "channel": channel_USD.slug,
        }
    }

    response = api_client.post_graphql(MUTATION_CHECKOUT_CREATE, variables)
    content = 