from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
import pytz
from django.core.exceptions import ValidationError

from ....order.error_codes import OrderErrorCode
from ....plugins.manager import get_plugins_manager
from ....product.models import ProductVariant
from ..utils import validate_draft_order


def test_validate_draft_order(draft_order):
    # should not raise any errors
    assert validate_draft_order(draft_order, "US", get_plugins_manager()) is None


def test_validate_draft_order_without_sku(draft_order):
    ProductVariant.objects.update(sku=None)
    draft_order.lines.update(product_sku=None)
    # should not raise any errors
    assert validate_draft_order(draft_order, "US", get_plugins_manager()) is None


def test_validate_draft_order_wrong_shipping(draft_order):
    order = draft_order
    shipping_zone = order.shipping_method.shipping_zone
    shipping_zone.countries = ["DE"]
    shipping_zone.save()
    assert order.shipping_address.country.code not in shipping_zone.countries
    with pytest.raises(ValidationError) as e:
        validate_draft_order(order, "US", get_plugins_manager())
    msg = "Shipping method is not valid for chosen shipping address"
    assert e.value.error_dict["shipping"][0].message == msg


def test_validate_draft_order_no_order_lines(order, shipping_method):
    order.shipping_method = shipping_method
    with pytest.raises(ValidationError) as e:
        validate_draft_order(order, "US", get_plugins_manager())
    msg = "Could not create order without any products."
    assert e.value.er