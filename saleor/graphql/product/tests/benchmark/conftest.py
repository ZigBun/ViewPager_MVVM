import pytest

from .....discount.models import Sale, SaleChannelListing
from .....product.models import Category


@pytest.fixture
def sales_list(channel_USD):
    sales = Sale.objects.bulk_create([Sale(name="Sale1"), Sale(name="Sale2")])
    values = [15, 5]
    SaleChannelListing.objects.bulk_create(
        [
            SaleChannelListing(
                sale=sale,
                channel=channel_USD,
                discount_value=values[i],
                currency=channel_USD.currency_code,
            )
            for i, sale in enumerate(sales)
        ]
    )
    return list(sales)


@pytest.fixture
def category_with_products(
    categories_tree,
    category,
    product_with_image,
    product_list_published,
    product_with_variant_with_two_attributes,
    product_with_multiple_values_attributes,
    product_without_shipping,
    sales_list,
):
    category = categories_tree
    child = Category.objects.create(name="TestCategory", slug="test-cat")
    child_2 = Category.objects.create(name="TestCatego