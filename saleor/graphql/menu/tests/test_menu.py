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
    menus = content["data"]["menus"]["edges"]
    assert len(menus) == 1
    assert menus[0]["node"]["slug"] == "menu3-slug"


def test_menus_query_with_slug_list_filter(staff_api_client, permission_manage_menus):
    Menu.objects.create(name="Menu1", slug="Menu1")
    Menu.objects.create(name="Menu2", slug="Menu2")
    Menu.objects.create(name="Menu3", slug="Menu3")
    variables = {"filter": {"slug": ["Menu2", "Menu3"]}}
    staff_api_client.user.user_permissions.add(permission_manage_menus)
    response = staff_api_client.post_graphql(QUERY_MENU_WITH_FILTER, variables)
    content = get_graphql_content(response)
    menus = content["data"]["menus"]["edges"]
    slugs = [node["node"]["slug"] for node in menus]
    assert len(menus) == 2
    assert "Menu2" in slugs
    assert "Menu3" in slugs


QUERY_MENU_WITH_SORT = """
    query ($sort_by: MenuSortingInput!) {
        menus(first:5, sortBy: $sort_by) {
            edges{
                node{
                    name
                }
            }
        }
    }
"""


@pytest.mark.parametrize(
    "menu_sort, result_order",
    [
        # We have "footer" and "navbar" from default saleor configuration
        ({"field": "NAME", "direction": "ASC"}, ["footer", "menu1", "navbar"]),
        ({"field": "NAME", "direction": "DESC"}, ["navbar", "menu1", "footer"]),
        ({"field": "ITEMS_COUNT", "direction": "ASC"}, ["footer", "navbar", "menu1"]),
        ({"field": "ITEMS_COUNT", "direction": "DESC"}, ["menu1", "navbar", "footer"]),
    ],
)
def test_query_menus_with_sort(
    menu_sort, result_order, staff_api_client, permission_manage_menus
):
    menu = Menu.objects.create(name="menu1", slug="menu1")
    MenuItem.objects.create(name="MenuItem1", menu=menu)
    MenuItem.objects.create(name="MenuItem2", menu=menu)
    navbar = Menu.objects.get(name="navbar")
    MenuItem.objects.create(name="NavbarMenuItem", menu=navbar)
    variables = {"sort_by": menu_sort}
    staff_api_client.user.user_permissions.add(permission_manage_menus)
    response = staff_api_client.post_graphql(QUERY_MENU_WITH_SORT, variables)
    content = get_graphql_content(response)
    menus = content["data"]["menus"]["edges"]

    for order, menu_name in enumerate(result_order):
        assert menus[order]["node"]["name"] == menu_name


QUERY_MENU_ITEM_BY_ID = """
query menuitem($id: ID!, $channel: String) {
    menuItem(id: $id, channel: $channel) {
        name
        children {
            name
        }
        collection {
            name
        }
        category {
            id
        }
        page {
            id
        }
        url
    }
}
"""


def test_menu_item_query(user_api_client, menu_item, published_collection, channel_USD):
    query = QUERY_MENU_ITEM_BY_ID
    menu_item.collection = published_collection
    menu_item.url = None
    menu_item.save()
    child_menu = MenuItem.objects.create(
        menu=menu_item.menu, name="Link 2", url="http://example2.com/", parent=menu_item
    )
    variables = {
        "id": graphene.Node.to_global_id("MenuItem", menu_item.pk),
        "channel": channel_USD.slug,
    }
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["menuItem"]
    assert data["name"] == menu_item.name
    assert len(data["children"]) == 1
    assert data["children"][0]["name"] == child_menu.name
    assert data["collection"]["name"] == published_collection.name
    assert not data["category"]
    assert not data["page"]
    assert data["url"] is None


def test_menu_item_query_with_invalid_channel(
    user_api_client, menu_item, published_collection, channel_USD
):
    query = QUERY_MENU_ITEM_BY_ID
    menu_item.collection = published_collection
    menu_item.url = None
    menu_item.save()
    child_menu = MenuItem.objects.create(
        menu=menu_item.menu, name="Link 2", url="http://example2.com/", parent=menu_item
    )
    variables = {
        "id": graphene.Node.to_global_id("MenuItem", menu_item.pk),
        "channel": "invalid",
    }
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["menuItem"]
    assert data["name"] == menu_item.name
    assert len(data["children"]) == 1
    assert data["children"][0]["name"] == child_menu.name
    assert not data["collection"]
    assert not data["category"]
    assert not data["page"]
    assert data["url"] is None


def test_staff_query_menu_item_by_invalid_id(staff_api_client, menu_item):
    id = "bh/"
    variables = {"id": id}
    response = staff_api_client.post_graphql(QUERY_MENU_ITEM_BY_ID, variables)
    content = get_graphql_content_from_response(response)
    assert len(content["errors"]) == 1
    assert content["errors"][0]["message"] == f"Couldn't resolve id: {id}."
    assert content["data"]["menuItem"] is None


def test_staff_query_menu_item_with_invalid_object_type(staff_api_client, menu_item):
    variables = {"id": graphene.Node.to_global_id("Order", menu_item.pk)}
    response = staff_api_client.post_graphql(QUERY_MENU_ITEM_BY_ID, variables)
    content = get_graphql_content(response)
    assert content["data"]["menuItem"] is None


def test_menu_items_query(
    user_api_client, menu_with_items, published_collection, channel_USD, category
):
    query = """
    fragment SecondaryMenuSubItem on MenuItem {
        id
        name
        category {
            id
            name
        }
        url
        collection {
            id
            name
        }
        page {
            slug
        }
    }
    query menuitem($id: ID!, $channel: String) {
        menu(id: $id, channel: $channel) {
            items {
                ...SecondaryMenuSubItem
                children {
                ...SecondaryMenuSubItem
                }
            }
        }
    }
    """
    variables = {
        "id": graphene.Node.to_global_id("Menu", menu_with_items.pk),
        "channel": channel_USD.slug,
    }
    response = user_api_client.post_graphql(query, variables)

    content = get_graphql_content(response)

    items = content["data"]["menu"]["items"]
    assert not items[0]["category"]
    assert not items[0]["collection"]
    assert items[1]["children"][0]["category"]["name"] == category.name
    assert items[1]["children"][1]["collection"]["name"] == published_collection.name


def test_menu_items_collection_in_other_channel(
    user_api_client, menu_item, published_collection, channel_PLN
):
    query = """
    query menuitem($id: ID!, $channel: String) {
        menuItem(id: $id, channel: $channel) {
            name
            children {
                name
            }
            collection {
                name
            }
            menu {
                slug
            }
            category {
                id
            }
            page {
                id
            }
            url
        }
    }
    """
    menu_item.collection = published_collection
    menu_item.url = None
    menu_item.save()
    child_menu = MenuItem.objects.create(
        menu=menu_item.menu, name="Link 2", url="http://example2.com/", parent=menu_item
    )
    variables = {
        "id": graphene.Node.to_global_id("MenuItem", menu_item.pk),
        "channel": channel_PLN.slug,
    }
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["menuItem"]
    assert data["name"] == menu_item.name
    assert data["menu"]["slug"] == menu_item.menu.slug
    assert len(data["children"]) == 1
    assert data["children"][0]["name"] == child_menu.name
    assert not data["collection"]
    assert not data["category"]
    assert not data["page"]
  