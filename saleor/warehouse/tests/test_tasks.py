from datetime import timedelta

import pytest
from django.utils import timezone

from ..models import PreorderReservation, Reservation
from ..tasks import (
    delete_expired_reservations_task,
    update_stocks_quantity_allocated_task,
)


def test_delete_expired_reservations_task_deletes_expired_stock_reservations(
    checkout_line_with_reservation_in_many_stocks,
):
    Reservation.objects.update(reserved_until=timezone.now() - timedelta(seconds=1))
    delete_expired_reservations_task()
    assert not Reservation.objects.exists()


def test_delete_expired_reservations_task_skips_active_stock_reservations(
    checkout_line_with_reservation_in_many_stocks,
):
    rese