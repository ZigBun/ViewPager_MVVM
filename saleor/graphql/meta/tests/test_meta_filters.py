import pytest

from ....product.models import Product
from ...tests.utils import get_graphql_content

FILTER_BY_META_QUERY = """
query filterProductsByMetadata ($filter:ProductFilterInput, $channel: String){
  products(first: 100, channel: $channel, filter: $filter){
    edges {
      node {
        slug
        metadata {
          key
          value
        }
      }
    }
  }
}
"""


@pytest.mark.parametrize(
    "metadata, total_count",
    [
        (
            [
                {
                    "key": "A",
                    "value": "1",
                },
                {
                    "key": "B",
                    "value": "2",
                },
                {
                    "key": "C",
                    "value": "3",
                },
            ],
            1,
        ),
        (
            [
                {
                    "key": "A",
                    "value": "1",
                },
                {
                    "key": "B",
                    "value": "2",
                },
            ],
            1,
        ),
        (
            [
                {
                    "key": "C",
                    "value": "3",
                },
            ],
            2,
        ),
        (
            [
                {
                    "key": "C",
                    "value": "44",
                },
            ],
            0,
        ),
        (
            [
                {
                    "key": "C",
                    "value": None,
                },
            ],
            2,
        ),
        (
            [
                {
                    "key": "A",
                    "value": None,
                },
                {
                    "key": "B",
                },
            ],
            1,
        ),
    ],
)
def test_filter_by_meta_total_returned_objects(
    metadata, total_count, api_client, product_list, channel_USD
):
    product1, product2, product3 = product_list
    variables = {
        "channel": channel_USD.slug,
        "filter": {
            "metadata": metadata,
        },
    }
    product1.store_value_in_metadata({"A": "1", "B": "2", "C": "3"})
    product2.store_value_in_metadata({"C": "3", "Z": "4"})
    Product.objects.bulk_update([product1, product2], ["metadata"])

    response = api_client.post_graphql(FILTER_BY_META_QUERY, variables)
    content = get_graphql_content(response)
    assert len(content["data"]["products"]["edges"]) == total_count


def test_filter_by_meta_expected_product_for_key_and_value(
    api_client, product_list, channel_USD
)