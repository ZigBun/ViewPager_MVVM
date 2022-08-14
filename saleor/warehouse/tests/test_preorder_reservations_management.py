from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from ...checkout.models import Checkout
from ...core.exceptions import InsufficientStock
from ...product.models import ProductVariantChannelListing
from ..models import PreorderAllocation, PreorderReservation
from ..reservations import reserve_preorders

COUNTRY_CODE = "US"
RESERVATION_LENGTH = 5


def test_reserve_preorders(checkout_line_with_preorder_item, channel_USD):
    checkout_line = checkout_line_with_preorder_item
    checkout_line.quantity = 5
    checkout_line.save()

    reserve_preorders(
        [checkout_line],
        [checkout_line.variant],
        COUNTRY_CODE,
        channel_USD.slug,
        timezone.now() + timedelta(minutes=RESERVATION_LENGTH),
    )

    reservation = PreorderReservation.objects.get(checkout_line=checkout_line)
    assert reservation.quantity_reserved == 5
    assert reservation.reserved_until > timezone.now() + timedelta(minutes=1)


def test_preorder_reservation_skips_prev_reservation_delete_if_replace_is_disabled(
    checkout_line_with_preorder_item, assert_num_queries, channel_USD
):
    checkout_line = checkout_line_with_preorder_item

    with assert_num_queries(3):
        reserve_preorders(
            [checkout_line],
            [checkout_line.variant],
            COUNTRY_CODE,
            channel_USD.slug,
            timezone.now() + timedelta(minutes=RESERVATION_LENGTH),
            replace=False,
        )

    with assert_num_queries(4):
        reserve_preorders(
            [checkout_line],
            [checkout_line.variant],
            COUNTRY_CODE,
            channel_USD.slug,
            timezone.now() + timedelta(minutes=RESERVATION_LENGTH),
        )


def test_preorder_reservation_removes_previous_reservations_for_checkout(
    checkout_line_with_preorder_item, channel_USD
):
    checkout_line = checkout_line_with_preorder_item
    checkout_line.quantity = 5
    checkout_line.save()

    previous_reservation = PreorderReservation.objects.create(
        checkout_line=checkout_line,
        product_variant_channel_listing=checkout_line.variant.channel_listings.first(),
        quantity_reserved=5,
        reserved_until=timezon