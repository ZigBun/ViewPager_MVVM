from unittest import mock

import graphene
import pytest
from django.test import override_settings
from graphql.execution.base import ExecutionResult

from .... import __version__ as saleor_version
from ....demo.views import EXAMPLE_QUERY
from ....graphql.utils import INTERNAL_ERROR_MESSAGE
from ...tests.fixtures import API_PATH
from ...tests.utils import get_graphql_content, get_graphql_content_from_response
from ...views import generate_cache_key


def test_batch_queries(category, product, api_client, channel_USD):
    query_product = """
        query GetProduct($id: ID!, $channel: String) {
            product(id: $id, channel: $channel) {
                name
            }
        }
    """
    query_category = """
        query GetCategory($id: ID!) {
            category(id: $id) {
                name
            }
        }
    """
    data = [
        {
            "query": query_category,
            "variables": {
                "id": graphene.Node.to_global_id("Category", category.pk),
                "channel": channel_USD.slug,
            },
        },
        {
            "query": query_product,
            "variables": {
                "id": graphene.Node.to_global_id("Product", product.pk),
                "channel": channel_USD.slug,
            },
        },
    ]
    response = api_client.post(data)
    batch_content = get_graphql_content(response)
    assert "errors" not in batch_content
    assert isinstance(batch_content, list)
    assert len(batch_content) == 2

    data = {
        field: value
        for content in batch_content
        for field, value in content["data"].items()
    }
    assert data["product"]["name"] == product.name
    assert data["category"]["name"] == category.name


def test_graphql_view_query_with_invalid_object_type(
    staff_api_client, product, permission_manage_orders, graphql_log_handler
):
    query = """
    query($id: ID!) {
        order(id: $id){
            token
        }
    }
    """
    variables = {
        "id": graphene.Node.to_global_id("Product", product.pk),
    }
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    response = staff_api_client.post_graphql(query, variables=variables)
    content = get_graphql_content(response)
    assert content["data"]["order"] is None


@pytest.mark.parametrize("playground_on, status", [(True, 200), (False, 405)])
def test_graphql_view_get_enabled_or_disabled(client, settings, playground_on, status):
    settings.PLAYGROUND_ENABLED = playground_on
    response = client.get(API_PATH)
    assert response.status_code == status


@pytest.mark.parametrize("method", ("put", "patch", "delete"))
def test_graphql_view_not_allowed(method, client):
    func = getattr(client, method)
    response = func(API_PATH)
    assert response.status_code == 405


def test_invalid_request_body_non_debug(client):
    data = "invalid-data"
    response = client.post(API_PATH, data, content_type="application/json")
    assert response.status_code 