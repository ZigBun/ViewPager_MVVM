from functools import partial
from unittest import mock
from unittest.mock import Mock

import graphene
import pytest
from django.urls import reverse
from graphql.error import GraphQLError
from graphql_relay import to_global_id

from ....order import models as order_models
from ...core.utils import from_global_id_or_error
from ...order.types import Order
from ...product.types import Product
from ...tests.utils import get_graphql_content
from ...utils import get_nodes


def test_middleware_dont_generate_sql_requests(client, settings, assert_num_queries):
    """When requesting on the GraphQL API endpoint, no SQL request should happen
    indirectly. This test ensures that."""

    # Enables the Graphql playground
    settings.DEBUG = True

    with assert_num_queries(0):
        response = client.get(reverse("api"))
        assert response.status_code == 200


def test_jwt_middleware(client, admin_user):
    user_details_query = """
        {
          me {
            email
          }
        }
    """

    create_token_query = """
        mutation {
          tokenCreate(email: "admin@example.com", password: "password") {
            token
          }
        }
    """

    api_url = reverse("api")
    api_client_post = partial(client.post, api_url, co