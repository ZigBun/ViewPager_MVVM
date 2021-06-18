from datetime import timedelta
from unittest import mock
from unittest.mock import patch

import graphene
from django.utils import timezone
from freezegun import freeze_time

from ....checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from ....checkout.utils import invalidate_checkout_prices
from ....plugins.manager import get_plugins_manager
from ...tests.utils import get_graphql_content

ADD_CHECKOUT_LINES = """
mutation addCheckoutLines($checkoutId: ID!, $line: CheckoutLineInput!) {
  checkoutLinesAdd(checkoutId: $checkoutId, lines: [$line]) {
    errors {
      field
      message
    }
  }
}
"""


@patch(
    "saleor.graphql.checkout.mutations.checkout_lines_add.invalidate_checkout_prices"
)
def test_checkout_lines_add_invalidate_prices(
    mocked_function,
    api_client,
    checkout_with_items,
    stock,
):
    # given
    manager = get_plugins_manager()
    query = ADD_CHECKOUT_LINES
    variables = {
        "checkoutId": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "line": {
            "quantity": 1,
            "variantId": graphene.Node.to_global_id(
                "ProductVariant", stock.product_variant.pk
            ),
        },
    }

    # when
    response = get_graphql_content(api_client.post_graphql(query, variables))

    # then
    assert not response["data"]["checkoutLinesAdd"]["errors"]
    checkout_with_items.refresh_from_db()
    lines, _ = fetch_checkout_lines(checkout_with_items)
    checkout_info = fetch_checkout_info(checkout_with_items, lines, [], manager)
    mocked_function.assert_called_once_with(
        checkout_info, lines, mock.ANY, [], save=True
    )


UPDATE_CHECKOUT_LINES = """
mutation updateCheckoutLines($token: UUID!, $line: CheckoutLineUpdateInput!) {
  checkoutLinesUpdate(token: $token, lines: [$line]) {
    errors {
      field
      message
    }
  }
}
"""


@patch(
    "saleor.graphql.checkout.mutations.checkout_lines_add.invalidate_checkout_prices"
)
def test_checkout_lines_update_invalidate_prices(
    mocked_function,
    api_client,
    checkout_with_items,
    stock,
):
    # given
    manager = get_plugins_manager()
    query = UPDATE_CHECKOUT_LINES
    variables = {
        "token": checkout_with_items.token,
        "line": {
            "quantity": 1,
            "variantId": graphene.Node.to_global_id(
                "ProductVariant", stock.product_variant.pk
            ),
        },
    }

    # when
    response = get_graphql_content(api_client.post_graphql(query, variables))

    # then
    assert not response["data"]["checkoutLinesUpdate"]["errors"]
    checkout_with_items.refresh_from_db()
    lines, _ = fetch_checkout_lines(checkout_with_items)
    checkout_info = fetch_checkout_info(checkout_with_items, lines, [], manager)
    mocked_function.assert_called_once_with(
        checkout_info, lines, mock.ANY, [], save=True
    )


DELETE_CHECKOUT_LINES = """
mutation deleteCheckoutLines($token: UUID!, $lineId: ID!){
  checkoutLinesDelete(token: $token, linesIds: [$lineId]) {
    errors {
      field
      message
    }
  }
}
"""


@patch(
    "saleor.graphql.checkout.mutations.checkout_lines_delete.invalidate_checkout_prices"
)
def test_checkout_lines_delete_invalidate_prices(
    mocked_function,
    api_client,
    checkout_with_items,
):
    # given
    manager = get_plugins_manager()
    query = DELETE_CHECKOUT_LINES
    variables = {
        "token": checkout_with_items.token,
        "lineId": graphene.Node.to_global_id(
            "CheckoutLine", checkout_with_items.lines.first().pk
        ),
    }

    # when
    response = get_graphql_content(api_client.post_graphql(query, variables))

    # then
    assert not response["data"]["checkoutLinesDelete"]["errors"]
    checkout_with_items.refresh_from_db()
    lines, _ = fetch_checkout_lines(checkout_with_items)
    checkout_info = fetch_checkout_info(checkout_with_items, lines, [], manager)
    mocked_function.assert_called_once_with(
        checkout_info, lines, mock.ANY, [], save=True
    )


DELETE_CHECKOUT_LINE = """
mutation deleteCheckoutLine($token: UUID!, $lineId: ID!){
  checkoutLineDelete(token: $token, lineId: $lineId) {
    errors {
      field
      message
    }
  }
}
"""


@patch(
    "saleor.graphql.checkout.mutations.checkout_line_delete.invalidate_checkout_prices"
)
def test_checkout_line_delete_invalidate_prices(
    mocked_function,
    api_client,
    checkout_with_items,
):
    # given
    manager = get_plugins_manager()
    query = DELETE_CHECKOUT_LINE
    variables = {
        "token": checkout_with_items.token,
        "lineId": graphene.Node.to_global_id(
            "CheckoutLine", checkout_with_items.lines.first().pk
      