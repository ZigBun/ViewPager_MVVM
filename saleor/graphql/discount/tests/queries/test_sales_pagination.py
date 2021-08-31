
from decimal import Decimal

import pytest
from django.utils import timezone
from freezegun import freeze_time

from .....discount import DiscountValueType
from .....discount.models import Sale, SaleChannelListing
from ....tests.utils import get_graphql_content


@pytest.fixture
@freeze_time("2020-03-18 12:00:00")
def sales_for_pagination(channel_USD):
    now = timezone.now()
    sales = Sale.objects.bulk_create(
        [
            Sale(
                name="Sale1",
                start_date=now + timezone.timedelta(hours=4),
                end_date=now + timezone.timedelta(hours=14),
                type=DiscountValueType.PERCENTAGE,
            ),
            Sale(
                name="Sale2",
                end_date=now + timezone.timedelta(hours=1),
            ),
            Sale(
                name="Sale3",
                end_date=now + timezone.timedelta(hours=2),
                type=DiscountValueType.PERCENTAGE,
            ),
            Sale(
                name="Sale4",
                end_date=now + timezone.timedelta(hours=1),
            ),
            Sale(
                name="Sale15",
                start_date=now + timezone.timedelta(hours=1),
                end_date=now + timezone.timedelta(hours=2),
            ),
        ]
    )
    values = [Decimal("1"), Decimal("7"), Decimal("5"), Decimal("5"), Decimal("25")]
    SaleChannelListing.objects.bulk_create(
        [
            SaleChannelListing(
                discount_value=values[i],
                sale=sale,
                channel=channel_USD,
                currency=channel_USD.currency_code,
            )
            for i, sale in enumerate(sales)
        ]
    )
    return sales


QUERY_SALES_PAGINATION = """
    query (
        $first: Int, $last: Int, $after: String, $before: String,, $channel: String
        $sortBy: SaleSortingInput, $filter: SaleFilterInput
    ){
        sales(
            first: $first, last: $last, after: $after, before: $before,
            sortBy: $sortBy, filter: $filter, channel: $channel
        ) {
            edges {
                node {
                    name
                }
            }
            pageInfo{
                startCursor
                endCursor
                hasNextPage
                hasPreviousPage
            }
        }
    }
"""


@pytest.mark.parametrize(
    "sort_by, sales_order",
    [
        ({"field": "NAME", "direction": "ASC"}, ["Sale1", "Sale15", "Sale2"]),
        ({"field": "NAME", "direction": "DESC"}, ["Sale4", "Sale3", "Sale2"]),