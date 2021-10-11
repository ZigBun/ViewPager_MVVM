import json
from unittest import mock

import graphene
import pytest
from django.core.exceptions import ValidationError
from django.utils.functional import SimpleLazyObject
from freezegun import freeze_time

from ....core.utils.json_serializer import CustomJsonEncoder
from ....menu.error_codes import MenuErrorCode
from ....menu.models import Menu, MenuItem
from ....product.models import Category
from ....webhook.event_types import WebhookEventAsyncType
from ....webhook.payloads import generate_meta, generate_requestor
from ...menu.mutations import NavigationType, _validate_menu_item_instance
from ...tests.utils import (
    assert_no_permission,
    get_graphql_content,
    get_graphql_content_from_response,
)


def test_validate_menu_item_instance(category, page):
    _validate_menu_item_instance({"category": category}, "category", Category)
    with pytest.raises(ValidationError):
        _validate_menu_item_instance({"category": page}, "category", Category)

    # test that validation passes with empty values passed in input
    _validate_menu_item_instance({}, "category", Category)
    _validate_menu_item_instance({"category": None}, "category", Category)


QUERY_MENU = """
    query ($id: ID, $name: String, $slug: String){
        menu(
            id: $id,
            name: $name,
            slug: $slug
        ) {
            id
            name
            slug
        }
    }
    """


def test_menu_query_by_id(
    user_api_client,
    menu,
):
    variables = {"id": graphene.Node.to_global_id("Menu", menu.pk)}

    response = user_api_client.post_graphql(QUERY_MENU, variables=variables)
    content = get_graphql_content(response)
    menu_data = content["data"]["menu"]
    assert menu_data is not None
    assert menu_data["name"] == menu.name


def test_staff_query_menu_by_invalid_id(staff_api_client, menu):
    id = "bh/"
    variables = {"id": id}
    response = staff_api_client.post_graphql(QUERY_MENU, variables)
    content = get_graphql_content_from_response(response)
    assert len(content["errors"]) == 1
    assert content["errors"][0]["message"] == f"Couldn't resolve id: {id}."
    assert content["data"]["menu"] is None


def test_staff_query_menu_with_invalid_object_type(staff_api_client, menu):
    variables = {"id": graphene.Node.to_global_id("Order", menu.pk)}
    response = staff_api_client.post_graphql(QUERY_MENU, variables)
    content = get_graphql_content(response)
    assert content["data"]["menu"] is None


def test_menu_query_by_name(
    user_api_client,
    menu,
):
    variables = {"name": menu.name}
    response = user_api_client.post_graphql(QUERY_MENU, variables=variables)
    content = get_graphql_content(response)
    menu_data = content["data"]["menu"]
    assert menu_data is not None
    assert menu_data["name"] == menu.name


def test_menu_query_by_slug(user_api_client):
    menu = Menu.objects.create(name="test_menu_name", slug="test_menu_name")
    variables = {"slug": menu.slug}
    response = user_api_client.post_graphql(QUERY_MENU, variables=variables)
    content = get_graphql_content(response)
    menu_data = content["data"]["menu"]
    assert menu_data is not None
    assert menu_data["name"] == menu.name
    assert menu_data["slug"] == menu.slug


def test_menu_query_error_when_id_and_name_provided(
    user_api_client,
    menu,
    graphql_log_handler,
):
    variables = {
        "id": graphene.Node.to_global_id("Menu", menu.pk),
        "name": menu.name,
    }
    response = user_api_client.post_graphql(QUERY_MENU, variables=variables)
    assert graphql_log_handler.messages == [
        "saleor.graphql.errors.handled[INFO].GraphQLError"
    ]
    content = get_graphql_content(response, ignore_errors=True)
    assert len(content["errors"]) == 1


def test_menu_query_error_when_no_param(
    user_api_client,
    menu,
    graphql_log_handler,
):
    variables = {}
    response = user_api_client.post_graphql(QUERY_MENU, variables=variables)
    assert graphql_log_handler.messages == [
        "saleor.graphql.errors.handled[INFO].GraphQLError"
    ]
    content = get_graphql_content(response, ignore_errors=True)
    assert len(content["errors"]) == 1


def test_menu_query(user_api_client, menu):
    query = """
    query menu($id: ID, $menu_name: String){
        menu(id: $id, name: $menu_name) {
            name
        }
    }
    """

    # test query by name
    variables = {"menu_name": menu.name}
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    assert content["data"]["menu"]["name"] == menu.name

    # test query by id
    menu_id = graphene.Node.to_global_id("Menu", menu.id)
    variables = {"id": menu_id}
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    assert content["data"]["menu"]["name"] == menu.name

    # test query by invalid name returns null
    variables = {"menu_name": "not-a-menu"}
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    assert not content["data"]["menu"]


QUERY_MENU_WITH_FILTER = """
    query ($filter: MenuFilterInput) {
        menus(first: 5, filter:$filter) {
            totalCount
            edges {
                node {
                    id
                    name
                    slug
                }
            }
        }
    }
"""


@pytest.mark.parametrize(
    "menu_filter, count",
    [
        ({"search": "Menu1"}, 1),
        ({"search": "Menu"}, 2),
        ({"slugs": ["Menu1", "Menu2"]}, 2),
        ({"slugs": []}, 4),
    ],
)
def test_menus_query_with_filter(
    menu_filter, count, staff_api_client, permission_manage_menus
):
    Menu.objects.create(name="Menu1", slug="Menu1")
    Menu.objects.create(name="Menu2", slug="Menu2")
    variables = {"filter": menu_filter}
    staff_api_client.user.user_permissions.add(permission_manage_menus)
    response = staff_api_client.post_graphql(QUERY_MENU_WITH_FILTER, variables)
    content = get_graphql_content(response)
    assert content["data"]["menus"]["totalCount"] == count


def test_menus_query_with_slug_filter(staff_api_client, permission_manage_menus):
    Menu.objects.create(name="Menu1", slug="Menu1")
    Menu.objects.create(name="Menu2", slug="Menu2")
    Menu.objects.create(name="Menu3", slug="menu3-slug")
    variables = {"filter": {"search": "menu3-slug"}}
    staff_api_client.user.user_permissions.add(permission_manage_menus)
    response = staff_api_client.post_graphql(QUERY_MENU_WITH_FILTER, variables)
    content = get_graphql_content(response)
    menus = conte