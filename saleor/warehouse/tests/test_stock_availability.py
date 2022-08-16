import pytest

from ...checkout.fetch import fetch_checkout_lines
from ...core.exceptions import InsufficientStock
from ..availability import (
    _get_available_quantity,
    check_stock_quantity,
    check_stock_quantity_bulk,
    get_available_quantity,
)
from ..models import Allocation

COUNTRY_CODE = "US"


def test_check_stock_quantity(variant_with_many_stocks, channel_USD):
    assert (
        check_stock_quantity(
            variant_with_many_stocks, COUNTRY_CODE, channel_USD.slug, 7
        )
        is None
    )


def test_check_stock_quantity_out_of_stock(variant_with_many_stocks, channel_USD):
    with pytest.raises(InsufficientStock):
        check_stock_quantity(
            variant_with_many_stocks, COUNTRY_CODE, channel_USD.slug, 8
        )


def test_check_stock_quantity_with_allocations(
    variant_with_many_stocks,
    order_line_with_allocation_in_many_stocks,
    order_line_with_one_allocation,
    channel_USD,
):
    assert (
        check_stock_quantity(
            variant_with_many_stocks, COUNTRY_CODE, channel_USD.slug, 3
        )
        is None
    )


def test_check_stock_quantity_with_allocations_out_of_stock(
    variant_with_many_stocks, order_line_with_allocation_in_many_stocks, channel_USD
):
    with pytest.raises(InsufficientStock):
        check_stock_quantity(
            variant_with_many_stocks, COUNTRY_CODE, channel_USD.slug, 5
        )


def test_check_stock_quantity_with_reservations(
    variant_with_many_stocks,
    checkout_line_with_reservation_in_many_stocks,
    checkout_line_with_one_reservation,
    channel_USD,
):
    assert (
        