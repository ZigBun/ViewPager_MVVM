from unittest import mock
from unittest.mock import patch

import graphene
import pytest

from .....account.models import Address
from .....checkout.error_codes import CheckoutErrorCode
from .....checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from .....checkout.utils import PRIVATE_META_APP_SHIPPING_ID, invalidate_checkout_prices
from .....plugins.manager import get_plugins_manager
from .....shipping import models as shipping_models
from .....shipping.utils import convert_to_shipping_method_data
from ....core.utils import to_global_id_or_none
from ....tests.utils import get_graphql_content

MUTATION_UPDATE_DELIVERY_METHOD = """
    mutation checkoutDeliveryMethodUpdate(
            $id: ID, $deliveryMethodId: ID) {
        checkoutDeliveryMethodUpdate(
            id: $id,
            deliveryMethodId: $deliveryMethodId) {
            checkout {
            id
            deliveryMethod {
                __typename
                ... on ShippingMethod {
                    name
                    id
                    translation(languageCode: EN_US) {
                        name
                    }
                }
                ... on Warehouse {
                   name
                   id
                }
            }
        }
        errors {
            field
            message
            code
        }
    }
}
"""


@pytest.mark.parametrize("is_valid_delivery_method", (True, False))
@pytest.mark.parametrize(
    "delivery_method, node_name, attribute_name",
    [
        ("warehouse", "Warehouse", "collection_point"),
        ("shipping_method", "ShippingMethod", "shipping_method"),
    ],
    indirect=("delivery_method",),
)
@patch(
    "saleor.graphql.checkout.mutations.checkout_delivery_method_update."
    "clean_delivery_method"
)
@patch(
    "saleor.graphql.checkout.mutations.checkout_delivery_method_update."
    "invalidate_checkout_prices",
    wraps=invalidate_checkout_prices,
)
def test_checkout_delivery_method_update(
    mock_invalidate_checkout_prices,
    mock_clean_delivery,
    api_client,
    delivery_method,
    node_name,
    attribute_name,
    checkout_with_item_for_cc,
    is_valid_delivery_method,
):
    # given
    mock_clean_delivery.return_value = is_valid_delivery_method

    checkout = checkout_with_item_for_cc
    manager = get_plugins_manager()
    lines, _ =