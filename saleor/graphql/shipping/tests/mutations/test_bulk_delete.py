from unittest import mock

import graphene
import pytest

from .....shipping.models import ShippingMethod, ShippingZone
from ....tests.utils import get_graphql_content


@pytest.fixture
def shipping_method_list(shipping_zone):
    shipping_method_1 = ShippingMethod.objects.create(
        shipping_zone=shipping_zone, name="DHL"
    )
    shipping_method_2 = ShippingMethod.objects.create(
        shipping_zone=shipping_zone, name="DPD"
    )
    shipping_method_3 = ShippingMethod.objects.create(
        shipping_zone=shipping_zone, name="GLS"
    )
    return shipping_method_1, shipping_method_2, shipping_method_3


BULK_DELETE_SHIPPING_PRICE_MUTATION = """
    mutation shippingPriceBulkDelete($ids: [ID!]!) {
        shippingPriceBulkDelete(ids: $ids) {
            count
        }
    }
"""


@pytest.fixture
def shipping_zone_list():
    shipping_zone_1 = ShippingZone.objects.create(name="Europe")
    shipping_zone_2 = ShippingZone.objects.create(name="Asia")
    shipping_zone_3 = ShippingZone.objects.create(name="Oceania")
    return shipping_zone_1, shipping_zone_2, shippin