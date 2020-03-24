from unittest.mock import patch

import graphene
import pytest

from .....warehouse.models import Stock, Warehouse
from ....tests.utils import get_graphql_content


@pytest.mark.django_db
@pytest.mark.count_queries(autouse=False)
@patch("saleor.plugins.manager.PluginsManager.product_variant_back_in_stock")
def test_product_variants_stocks_create(
    product_variant_back_in_stock_webhook_mock,
    staff_api_client,
    variant,
    warehouse,
    permission_manage_products,
    count_queries,
):
    query = """
    mutation ProductVariantStocksCreate($variantId: ID!, $stocks: [StockInput!]!){
        productVariantStocksCreate(variantId: $variantId, stocks: $stocks){
            productVariant{
                stocks {
                    quantity
                    quantityAllocated
                    id
                    warehouse{
                        slug
                    }
                }
            }
            errors{
                code
                field
                message
                index
            }
        }
    }
    """
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    second_warehouse = Warehouse.objects.get(pk=warehouse.pk)
    second_warehouse.slug = "second warehouse"
    second_warehouse.pk = None
    second_warehouse.save()

    stocks_count = variant.stocks.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.id),
            "quantity": 20,
        },
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", second_warehouse.id),
            "quantity": 100,
        },
    ]
    variables = {"variantId": variant_id, "stocks": stocks}
    response = staff_api_client.post_graphql(
        query,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)
    data = content["data"]["productVariantStocksCreate"]
    assert not data["errors"]
    assert (
        len(data["productVariant"]["stocks"])
        == variant.stocks.count()
        == stocks_count + len(stocks)
    )
    assert product_variant_back_in_stock_webhook_mock.call_count == 2
    product_variant_back_in_stock_webhook_mock.assert_called_with(Stock.objects.last())


@pytest.mark.django_db
@pytest.mark.count_queries(autouse=False)
@patch("saleor.plugins.manager.PluginsManager.product_variant_back_in_stock")
def test_product_variants_stocks_create_with_single_webhook_called(
    product_variant_back_in_stock_webhook_mock,
    staff_api_client,
    variant,
    warehouse,
    permission_manage_products,
    count_queries,
):
    query = """
    mutation ProductVariantStocksCreate($variantId: ID!, $stocks: [StockInput!]!){
        productVariantStocksCreate(variantId: $variantId, stocks: $stocks){
            productVariant{
                stocks {
                    quantity
                    quantityAllocated
                    id
                    warehouse{
                        slug
                    }
                }
            }
            errors{
                code
                field
                message
                index
            }
        }
    }
    """
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    second_warehouse = Warehouse.objects.get(pk=warehouse.pk)
    second_warehouse.slug = "second warehouse"
    second_warehouse.pk = None
    second_warehouse.save()

    stocks_count = variant.stocks.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.id),
            "quantity": 20,
        },
    ]
    variables = {"variantId": variant_id, "stocks": stocks}
    response = staff_api_client.post_graphql(
        query,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)
    data = content["data"]["productVariantStocksCreate"]
    assert not data["errors"]
    assert (
        len(data["productVariant"]["stocks"])
        == variant.stocks.count()
        == stocks_count + len(stocks)
    )
    product_variant_back_in_stock_webhook_mock.assert_called_with(Stock.objects.last())


PRODUCT_VARIANT_STOCKS_UPDATE_MUTATION = """
mutation ProductVariantStocksUpdate(
    $variantId: ID, $sku: String, $stocks: [StockInput!]!){
        productVariantStocksUpdate(variantId: $variantId, sku: $sku, stocks: $stocks){
            productVariant{
                stocks{
                    quantity
                    quantityAllocated
                    id
                    warehouse{
                        slug
                    }
                }
            }
            errors{
                code
                field
                message
                index
            }
        }
    }
"""


@pytest.mark.django_db
@pytest.mark.count_queries(autouse=False)
def test_product_variants_stocks_update_byid(
    staff_api_client, variant, warehouse, permission_manage_products, count_queries
):
    variant_id = graphene.Node.to_global_id("ProductVariant", variant.pk)
    second_warehouse = Warehouse.objects.get(pk=warehouse.pk)
    second_warehouse.slug = "second warehouse"
    second_warehouse.pk = None
    second_warehouse.save()

    Stock.objects.create(product_variant=variant, warehouse=warehouse, quantity=10)

    stocks_count = variant.stocks.count()

    stocks = [
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", warehouse.id),
            "quantity": 20,
        },
        {
            "warehouse": graphene.Node.to_global_id("Warehouse", second_warehouse.id),
            "quantity": 100,
        },
    ]
    variables = {"variantId": variant_id, "stocks": stocks}
    response = staff_api_client.post_graphql(
        PRODUCT_VARIANT_STOCKS_UPDATE_MUTATION,
        variables,
        permissions=[permission_manage_products],
    )
    content = get_graphql_content(response)
    data = content["data"]["productVariantStocksUpdate