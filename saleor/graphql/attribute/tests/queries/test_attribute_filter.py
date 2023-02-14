
from unittest import mock

import graphene
import pytest

from .....attribute.models import Attribute
from .....attribute.utils import associate_attribute_values_to_instance
from .....product import ProductTypeKind
from .....product.models import ProductType
from ....tests.utils import get_graphql_content, get_graphql_content_from_response
from ...filters import filter_attributes_by_product_types

ATTRIBUTES_FILTER_QUERY = """
    query($filters: AttributeFilterInput!, $channel: String) {
      attributes(first: 10, filter: $filters, channel: $channel) {
        edges {
          node {
            name
            slug
          }
        }
      }
    }
"""

ATTRIBUTES_VALUE_FILTER_QUERY = """
query($filters: AttributeValueFilterInput!) {
    attributes(first: 10) {
        edges {
            node {
                name
                slug
                choices(first: 10, filter: $filters) {
                    edges {
                        node {
                            name
                            slug
                        }
                    }
                }
            }
        }
    }
}
"""


def test_search_attributes(api_client, color_attribute, size_attribute):
    variables = {"filters": {"search": "color"}}

    attributes = get_graphql_content(
        api_client.post_graphql(ATTRIBUTES_FILTER_QUERY, variables)