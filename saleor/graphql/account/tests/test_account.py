import datetime
import json
import os
import re
from collections import defaultdict
from datetime import timedelta
from unittest.mock import ANY, MagicMock, Mock, call, patch
from urllib.parse import urlencode

import graphene
import pytest
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.files import File
from django.test import override_settings
from django.utils import timezone
from django.utils.functional import SimpleLazyObject
from freezegun import freeze_time

from ....account import events as account_events
from ....account.error_codes import AccountErrorCode
from ....account.models import Address, Group, User
from ....account.notifications import get_default_user_payload
from ....account.search import (
    generate_address_search_document_value,
    generate_user_fields_search_document_value,
    prepare_user_search_document_value,
)
from ....checkout import AddressType
from ....core.jwt import create_token
from ....core.notify_events import NotifyEventType
from ....core.tests.utils import get_site_context_payload
from ....core.tokens import account_delete_token_generator
from ....core.utils.json_serializer import CustomJsonEncoder
from ....core.utils.url import prepare_url
from ....order import OrderStatus
from ....order.models import FulfillmentStatus, Order
from ....permission.enums import AccountPermissions, OrderPermissions
from ....product.tests.utils import create_image
from ....thumbnail.models import Thumbnail
from ....webhook.event_types import WebhookEventAsyncType
from ....webhook.payloads import (
    generate_customer_payload,
    generate_meta,
    generate_requestor,
)
from ...core.enums import ThumbnailFormatEnum
from ...core.utils import str_to_enum, to_global_id_or_none
from ...tests.utils import (
    assert_graphql_error_with_message,
    assert_no_permission,
    get_graphql_content,
    get_graphql_content_from_response,
    get_multipart_request_body,
)
from ..mutations.base import INVALID_TOKEN
from ..mutations.staff import CustomerDelete, StaffDelete, StaffUpdate, UserDelete
from ..tests.utils import convert_dict_keys_to_camel_case


def generate_address_webhook_call_args(address, event, requestor, webhook):
    return [
        json.dumps(
            {
                "id": graphene.Node.to_global_id("Address", address.id),
                "city": address.city,
                "country": {"code": address.country.code, "name": address.country.name},
                "company_name": address.company_name,
                "meta": generate_meta(
                    requestor_data=generate_requestor(
                        SimpleLazyObject(lambda: requestor)
                    )
                ),
            },
            cls=CustomJsonEncoder,
        ),
        event,
        [webhook],
        address,
        SimpleLazyObject(lambda: requestor),
    ]


@pytest.fixture
def query_customer_with_filter():
    query = """
    query ($filter: CustomerFilterInput!, ) {
        customers(first: 5, filter: $filter) {
            totalCount
            edges {
                node {
                    id
                    lastName
                    firstName
                }
            }
        }
    }
    """
    return query


@pytest.fixture
def query_staff_users_with_filter():
    query = """
    query ($filter: StaffUserInput!, ) {
        staffUsers(first: 5, filter: $filter) {
            totalCount
            edges {
                node {
                    id
                    lastName
                    firstName
                }
            }
        }
    }
    """
    return query


FULL_USER_QUERY = """
    query User($id: ID!) {
        user(id: $id) {
            email
            firstName
            lastName
            isStaff
            isActive
            addresses {
                id
                isDefaultShippingAddress
                isDefaultBillingAddress
            }
            checkoutIds
            orders(first: 10) {
                totalCount
                edges {
                    node {
                        id
                    }
                }
            }
            languageCode
            dateJoined
            lastLogin
            defaultShippingAddress {
                firstName
                lastName
                companyName
                streetAddress1
                streetAddress2
                city
                cityArea
                postalCode
                countryArea
                phone
                country {
                    code
                }
                isDefaultShippingAddress
                isDefaultBillingAddress
            }
            defaultBillingAddress {
                firstName
                lastName
                companyName
                streetAddress1
                streetAddress2
                city
                cityArea
                postalCode
                countryArea
                phone
                country {
                    code
                }
                isDefaultShippingAddress
                isDefaultBillingAddress
            }
            avatar {
                url
            }
            userPermissions {
                code
                sourcePermissionGroups(userId: $id) {
                    name
                }
            }
            permissionGroups {
                name
                permissions {
                    code
                }
            }
            editableGroups {
                name
            }
            giftCards(first: 10) {
                edges {
                    node {
                        id
                    }
                }
            }
            checkouts(first: 10) {
                edges {
                    node {
                        id
                    }
                }
            }
        }
    }
"""


def test_query_customer_user(
    staff_api_client,
    customer_user,
    gift_card_used,
    gift_card_expiry_date,
    address,
    permission_manage_users,
    permission_manage_orders,
    media_root,
    settings,
    checkout,
):
    user = customer_user
    user.default_shipping_address.country = "US"
    user.default_shipping_address.save()
    user.addresses.add(address.get_copy())

    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image.jpg"
    user.avatar = avatar_mock
    user.save()

    checkout.user = user
    checkout.save()

    Group.objects.create(name="empty group")

    query = FULL_USER_QUERY
    ID = graphene.Node.to_global_id("User", customer_user.id)
    variables = {"id": ID}
    staff_api_client.user.user_permissions.add(
        permission_manage_users, permission_manage_orders
    )
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert data["email"] == user.email
    assert data["firstName"] == user.first_name
    assert data["lastName"] == user.last_name
    assert data["isStaff"] == user.is_staff
    assert data["isActive"] == user.is_active
    assert data["orders"]["totalCount"] == user.orders.count()
    assert data["avatar"]["url"]
    assert data["languageCode"] == settings.LANGUAGE_CODE.upper()
    assert len(data["editableGroups"]) == 0

    assert len(data["addresses"]) == user.addresses.count()
    for address in data["addresses"]:
        if address["isDefaultShippingAddress"]:
            address_id = graphene.Node.to_global_id(
                "Address", user.default_shipping_address.id
            )
            assert address["id"] == address_id
        if address["isDefaultBillingAddress"]:
            address_id = graphene.Node.to_global_id(
                "Address", user.default_billing_address.id
            )
            assert address["id"] == address_id

    address = data["defaultShippingAddress"]
    user_address = user.default_shipping_address
    assert address["firstName"] == user_address.first_name
    assert address["lastName"] == user_address.last_name
    assert address["companyName"] == user_address.company_name
    assert address["streetAddress1"] == user_address.street_address_1
    assert address["streetAddress2"] == user_address.street_address_2
    assert address["city"] == user_address.city
    assert address["cityArea"] == user_address.city_area
    assert address["postalCode"] == user_address.postal_code
    assert address["country"]["code"] == user_address.country.code
    assert address["countryArea"] == user_address.country_area
    assert address["phone"] == user_address.phone.as_e164
    assert address["isDefaultShippingAddress"] is None
    assert address["isDefaultBillingAddress"] is None

    address = data["defaultBillingAddress"]
    user_address = user.default_billing_address
    assert address["firstName"] == user_address.first_name
    assert address["lastName"] == user_address.last_name
    assert address["companyName"] == user_address.company_name
    assert address["streetAddress1"] == user_address.street_address_1
    assert address["streetAddress2"] == user_address.street_address_2
    assert address["city"] == user_address.city
    assert address["cityArea"] == user_address.city_area
    assert address["postalCode"] == user_address.postal_code
    assert address["country"]["code"] == user_address.country.code
    assert address["countryArea"] == user_address.country_area
    assert address["phone"] == user_address.phone.as_e164
    assert address["isDefaultShippingAddress"] is None
    assert address["isDefaultBillingAddress"] is None
    assert len(data["giftCards"]) == 1
    assert data["giftCards"]["edges"][0]["node"]["id"] == graphene.Node.to_global_id(
        "GiftCard", gift_card_used.pk
    )
    assert data["checkoutIds"] == [to_global_id_or_none(checkout)]
    assert data["checkouts"]["edges"][0]["node"]["id"] == graphene.Node.to_global_id(
        "Checkout", checkout.pk
    )


def test_query_customer_user_with_orders(
    staff_api_client,
    customer_user,
    order_list,
    permission_manage_users,
    permission_manage_orders,
):
    # given
    query = FULL_USER_QUERY
    order_unfulfilled = order_list[0]
    order_unfulfilled.user = customer_user

    order_unconfirmed = order_list[1]
    order_unconfirmed.status = OrderStatus.UNCONFIRMED
    order_unconfirmed.user = customer_user

    order_draft = order_list[2]
    order_draft.status = OrderStatus.DRAFT
    order_draft.user = customer_user

    Order.objects.bulk_update(
        [order_unconfirmed, order_draft, order_unfulfilled], ["user", "status"]
    )

    id = graphene.Node.to_global_id("User", customer_user.id)
    variables = {"id": id}

    # when
    response = staff_api_client.post_graphql(
        query,
        variables,
        permissions=[permission_manage_users, permission_manage_orders],
    )

    # then
    content = get_graphql_content(response)
    user = content["data"]["user"]
    assert {order["node"]["id"] for order in user["orders"]["edges"]} == {
        graphene.Node.to_global_id("Order", order.pk) for order in order_list
    }


def test_query_customer_user_with_orders_no_manage_orders_perm(
    staff_api_client,
    customer_user,
    order_list,
    permission_manage_users,
):
    # given
    query = FULL_USER_QUERY
    order_unfulfilled = order_list[0]
    order_unfulfilled.user = customer_user

    order_unconfirmed = order_list[1]
    order_unconfirmed.status = OrderStatus.UNCONFIRMED
    order_unconfirmed.user = customer_user

    order_draft = order_list[2]
    order_draft.status = OrderStatus.DRAFT
    order_draft.user = customer_user

    Order.objects.bulk_update(
        [order_unconfirmed, order_draft, order_unfulfilled], ["user", "status"]
    )

    id = graphene.Node.to_global_id("User", customer_user.id)
    variables = {"id": id}

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )

    # then
    assert_no_permission(response)


def test_query_customer_user_app(
    app_api_client,
    customer_user,
    address,
    permission_manage_users,
    permission_manage_staff,
    permission_manage_orders,
    media_root,
    app,
):
    user = customer_user
    user.default_shipping_address.country = "US"
    user.default_shipping_address.save()
    user.addresses.add(address.get_copy())

    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image.jpg"
    user.avatar = avatar_mock
    user.save()

    Group.objects.create(name="empty group")

    query = FULL_USER_QUERY
    ID = graphene.Node.to_global_id("User", customer_user.id)
    variables = {"id": ID}
    app.permissions.add(
        permission_manage_staff, permission_manage_users, permission_manage_orders
    )
    response = app_api_client.post_graphql(query, variables)

    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert data["email"] == user.email


def test_query_customer_user_with_orders_by_app_no_manage_orders_perm(
    app_api_client,
    customer_user,
    order_list,
    permission_manage_users,
):
    # given
    query = FULL_USER_QUERY
    order_unfulfilled = order_list[0]
    order_unfulfilled.user = customer_user

    order_unconfirmed = order_list[1]
    order_unconfirmed.status = OrderStatus.UNCONFIRMED
    order_unconfirmed.user = customer_user

    order_draft = order_list[2]
    order_draft.status = OrderStatus.DRAFT
    order_draft.user = customer_user

    Order.objects.bulk_update(
        [order_unconfirmed, order_draft, order_unfulfilled], ["user", "status"]
    )

    id = graphene.Node.to_global_id("User", customer_user.id)
    variables = {"id": id}

    # when
    response = app_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )

    # then
    assert_no_permission(response)


def test_query_staff_user(
    staff_api_client,
    staff_user,
    address,
    permission_manage_users,
    media_root,
    permission_manage_orders,
    permission_manage_products,
    permission_manage_staff,
    permission_manage_menus,
):
    staff_user.user_permissions.add(permission_manage_orders, permission_manage_staff)

    groups = Group.objects.bulk_create(
        [
            Group(name="manage users"),
            Group(name="another user group"),
            Group(name="another group"),
            Group(name="empty group"),
        ]
    )
    group1, group2, group3, group4 = groups

    group1.permissions.add(permission_manage_users, permission_manage_products)

    # user groups
    staff_user.groups.add(group1, group2)

    # another group (not user group) with permission_manage_users
    group3.permissions.add(permission_manage_users, permission_manage_menus)

    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image2.jpg"
    staff_user.avatar = avatar_mock
    staff_user.save()

    query = FULL_USER_QUERY
    user_id = graphene.Node.to_global_id("User", staff_user.pk)
    variables = {"id": user_id}
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["user"]

    assert data["email"] == staff_user.email
    assert data["firstName"] == staff_user.first_name
    assert data["lastName"] == staff_user.last_name
    assert data["isStaff"] == staff_user.is_staff
    assert data["isActive"] == staff_user.is_active
    assert data["orders"]["totalCount"] == staff_user.orders.count()
    assert data["avatar"]["url"]

    assert len(data["permissionGroups"]) == 2
    assert {group_data["name"] for group_data in data["permissionGroups"]} == {
        group1.name,
        group2.name,
    }
    assert len(data["userPermissions"]) == 4
    assert len(data["editableGroups"]) == Group.objects.count() - 1
    assert {data_group["name"] for data_group in data["editableGroups"]} == {
        group1.name,
        group2.name,
        group4.name,
    }

    formated_user_permissions_result = [
        {
            "code": perm["code"].lower(),
            "groups": {group["name"] for group in perm["sourcePermissionGroups"]},
        }
        for perm in data["userPermissions"]
    ]
    all_permissions = group1.permissions.all() | staff_user.user_permissions.all()
    for perm in all_permissions:
        source_groups = {group.name for group in perm.group_set.filter(user=staff_user)}
        expected_data = {"code": perm.codename, "groups": source_groups}
        assert expected_data in formated_user_permissions_result


def test_query_staff_user_with_order_and_without_manage_orders_perm(
    staff_api_client,
    staff_user,
    order_list,
    permission_manage_staff,
):
    # given
    staff_user.user_permissions.add(permission_manage_staff)

    order_unfulfilled = order_list[0]
    order_unfulfilled.user = staff_user

    order_unconfirmed = order_list[1]
    order_unconfirmed.status = OrderStatus.UNCONFIRMED
    order_unconfirmed.user = staff_user

    order_draft = order_list[2]
    order_draft.status = OrderStatus.DRAFT
    order_draft.user = staff_user

    Order.objects.bulk_update(
        [order_unconfirmed, order_draft, order_unfulfilled], ["user", "status"]
    )

    query = FULL_USER_QUERY
    user_id = graphene.Node.to_global_id("User", staff_user.pk)
    variables = {"id": user_id}
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["user"]

    assert data["email"] == staff_user.email
    assert data["orders"]["totalCount"] == 2
    assert {node["node"]["id"] for node in data["orders"]["edges"]} == {
        graphene.Node.to_global_id("Order", order.pk)
        for order in [order_unfulfilled, order_unconfirmed]
    }


def test_query_staff_user_with_orders_and_manage_orders_perm(
    staff_api_client,
    staff_user,
    order_list,
    permission_manage_staff,
    permission_manage_orders,
):
    # given
    staff_user.user_permissions.add(permission_manage_staff, permission_manage_orders)

    order_unfulfilled = order_list[0]
    order_unfulfilled.user = staff_user

    order_unconfirmed = order_list[1]
    order_unconfirmed.status = OrderStatus.UNCONFIRMED
    order_unconfirmed.user = staff_user

    order_draft = order_list[2]
    order_draft.status = OrderStatus.DRAFT
    order_draft.user = staff_user

    Order.objects.bulk_update(
        [order_unconfirmed, order_draft, order_unfulfilled], ["user", "status"]
    )

    query = FULL_USER_QUERY
    user_id = graphene.Node.to_global_id("User", staff_user.pk)
    variables = {"id": user_id}
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["user"]

    assert data["email"] == staff_user.email
    assert data["orders"]["totalCount"] == 3
    assert {node["node"]["id"] for node in data["orders"]["edges"]} == {
        graphene.Node.to_global_id("Order", order.pk)
        for order in [order_unfulfilled, order_unconfirmed, order_draft]
    }


USER_QUERY = """
    query User($id: ID $email: String, $externalReference: String) {
        user(id: $id, email: $email, externalReference: $externalReference) {
            id
            email
            externalReference
        }
    }
"""


def test_query_user_by_email_address(
    user_api_client, customer_user, permission_manage_users
):
    email = customer_user.email
    variables = {"email": email}
    response = user_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert customer_user.email == data["email"]


def test_query_user_by_external_reference(
    user_api_client, customer_user, permission_manage_users
):
    # given
    user = customer_user
    ext_ref = "test-ext-ref"
    user.external_reference = ext_ref
    user.save(update_fields=["external_reference"])
    variables = {"externalReference": ext_ref}

    # when
    response = user_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["user"]
    assert data["externalReference"] == user.external_reference


def test_query_user_by_id_and_email(
    user_api_client, customer_user, permission_manage_users
):
    email = customer_user.email
    id = graphene.Node.to_global_id("User", customer_user.id)
    variables = {
        "id": id,
        "email": email,
    }
    response = user_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )
    assert_graphql_error_with_message(
        response, "Argument 'id' cannot be combined with 'email'"
    )


def test_customer_can_not_see_other_users_data(user_api_client, staff_user):
    id = graphene.Node.to_global_id("User", staff_user.id)
    variables = {"id": id}
    response = user_api_client.post_graphql(USER_QUERY, variables)
    assert_no_permission(response)


def test_user_query_anonymous_user(api_client):
    variables = {"id": ""}
    response = api_client.post_graphql(USER_QUERY, variables)
    assert_no_permission(response)


def test_user_query_permission_manage_users_get_customer(
    staff_api_client, customer_user, permission_manage_users
):
    customer_id = graphene.Node.to_global_id("User", customer_user.pk)
    variables = {"id": customer_id}
    response = staff_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert customer_user.email == data["email"]


def test_user_query_as_app(app_api_client, customer_user, permission_manage_users):
    customer_id = graphene.Node.to_global_id("User", customer_user.pk)
    variables = {"id": customer_id}
    response = app_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert customer_user.email == data["email"]


def test_user_query_permission_manage_users_get_staff(
    staff_api_client, staff_user, permission_manage_users
):
    staff_id = graphene.Node.to_global_id("User", staff_user.pk)
    variables = {"id": staff_id}
    response = staff_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    assert not content["data"]["user"]


def test_user_query_permission_manage_staff_get_customer(
    staff_api_client, customer_user, permission_manage_staff
):
    customer_id = graphene.Node.to_global_id("User", customer_user.pk)
    variables = {"id": customer_id}
    response = staff_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    assert not content["data"]["user"]


def test_user_query_permission_manage_staff_get_staff(
    staff_api_client, staff_user, permission_manage_staff
):
    staff_id = graphene.Node.to_global_id("User", staff_user.pk)
    variables = {"id": staff_id}
    response = staff_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert staff_user.email == data["email"]


@pytest.mark.parametrize("id", ["'", "abc"])
def test_user_query_invalid_id(
    id, staff_api_client, customer_user, permission_manage_users
):
    variables = {"id": id}
    response = staff_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )

    content = get_graphql_content_from_response(response)
    assert len(content["errors"]) == 1
    assert content["errors"][0]["message"] == f"Couldn't resolve id: {id}."
    assert content["data"]["user"] is None


def test_user_query_object_with_given_id_does_not_exist(
    staff_api_client, permission_manage_users
):
    id = graphene.Node.to_global_id("User", -1)
    variables = {"id": id}
    response = staff_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )

    content = get_graphql_content(response)
    assert content["data"]["user"] is None


def test_user_query_object_with_invalid_object_type(
    staff_api_client, customer_user, permission_manage_users
):
    id = graphene.Node.to_global_id("Order", customer_user.pk)
    variables = {"id": id}
    response = staff_api_client.post_graphql(
        USER_QUERY, variables, permissions=[permission_manage_users]
    )

    content = get_graphql_content(response)
    assert content["data"]["user"] is None


USER_AVATAR_QUERY = """
    query User($id: ID, $size: Int, $format: ThumbnailFormatEnum) {
        user(id: $id) {
            id
            avatar(size: $size, format: $format) {
                url
                alt
            }
        }
    }
"""


def test_query_user_avatar_with_size_and_format_proxy_url_returned(
    staff_api_client, media_root, permission_manage_staff, site_settings
):
    # given
    user = staff_api_client.user
    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image.jpg"
    user.avatar = avatar_mock
    user.save(update_fields=["avatar"])

    format = ThumbnailFormatEnum.WEBP.name

    user_id = graphene.Node.to_global_id("User", user.id)
    user_uuid = graphene.Node.to_global_id("User", user.uuid)
    variables = {"id": user_id, "size": 120, "format": format}

    # when
    response = staff_api_client.post_graphql(
        USER_AVATAR_QUERY, variables, permissions=[permission_manage_staff]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["user"]
    domain = site_settings.site.domain
    assert (
        data["avatar"]["url"]
        == f"http://{domain}/thumbnail/{user_uuid}/128/{format.lower()}/"
    )


def test_query_user_avatar_with_size_proxy_url_returned(
    staff_api_client, media_root, permission_manage_staff, site_settings
):
    # given
    user = staff_api_client.user
    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image.jpg"
    user.avatar = avatar_mock
    user.save(update_fields=["avatar"])

    user_id = graphene.Node.to_global_id("User", user.id)
    user_uuid = graphene.Node.to_global_id("User", user.uuid)
    variables = {"id": user_id, "size": 120}

    # when
    response = staff_api_client.post_graphql(
        USER_AVATAR_QUERY, variables, permissions=[permission_manage_staff]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert (
        data["avatar"]["url"]
        == f"http://{site_settings.site.domain}/thumbnail/{user_uuid}/128/"
    )


def test_query_user_avatar_with_size_thumbnail_url_returned(
    staff_api_client, media_root, permission_manage_staff, site_settings
):
    # given
    user = staff_api_client.user
    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image.jpg"
    user.avatar = avatar_mock
    user.save(update_fields=["avatar"])

    thumbnail_mock = MagicMock(spec=File)
    thumbnail_mock.name = "thumbnail_image.jpg"
    Thumbnail.objects.create(user=user, size=128, image=thumbnail_mock)

    id = graphene.Node.to_global_id("User", user.pk)
    variables = {"id": id, "size": 120}

    # when
    response = staff_api_client.post_graphql(
        USER_AVATAR_QUERY, variables, permissions=[permission_manage_staff]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert (
        data["avatar"]["url"]
        == f"http://{site_settings.site.domain}/media/thumbnails/{thumbnail_mock.name}"
    )


def test_query_user_avatar_original_size_custom_format_provided_original_image_returned(
    staff_api_client, media_root, permission_manage_staff, site_settings
):
    # given
    user = staff_api_client.user
    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image.jpg"
    user.avatar = avatar_mock
    user.save(update_fields=["avatar"])

    format = ThumbnailFormatEnum.WEBP.name

    id = graphene.Node.to_global_id("User", user.pk)
    variables = {"id": id, "format": format, "size": 0}

    # when
    response = staff_api_client.post_graphql(
        USER_AVATAR_QUERY, variables, permissions=[permission_manage_staff]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert (
        data["avatar"]["url"]
        == f"http://{site_settings.site.domain}/media/user-avatars/{avatar_mock.name}"
    )


def test_query_user_avatar_no_size_value(
    staff_api_client, media_root, permission_manage_staff, site_settings
):
    # given
    user = staff_api_client.user
    avatar_mock = MagicMock(spec=File)
    avatar_mock.name = "image.jpg"
    user.avatar = avatar_mock
    user.save(update_fields=["avatar"])

    id = graphene.Node.to_global_id("User", user.pk)
    variables = {"id": id}

    user_uuid = graphene.Node.to_global_id("User", user.uuid)

    # when
    response = staff_api_client.post_graphql(
        USER_AVATAR_QUERY, variables, permissions=[permission_manage_staff]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert (
        data["avatar"]["url"]
        == f"http://{site_settings.site.domain}/thumbnail/{user_uuid}/4096/"
    )


def test_query_user_avatar_no_image(staff_api_client, permission_manage_staff):
    # given
    user = staff_api_client.user

    id = graphene.Node.to_global_id("User", user.pk)
    variables = {"id": id}

    # when
    response = staff_api_client.post_graphql(
        USER_AVATAR_QUERY, variables, permissions=[permission_manage_staff]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["user"]
    assert data["id"]
    assert not data["avatar"]


def test_query_customers(staff_api_client, user_api_client, permission_manage_users):
    query = """
    query Users {
        customers(first: 20) {
            totalCount
            edges {
                node {
                    isStaff
                }
            }
        }
    }
    """
    variables = {}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    users = content["data"]["customers"]["edges"]
    assert users
    assert all([not user["node"]["isStaff"] for user in users])

    # check permissions
    response = user_api_client.post_graphql(query, variables)
    assert_no_permission(response)


def test_query_staff(
    staff_api_client, user_api_client, staff_user, admin_user, permission_manage_staff
):
    query = """
    {
        staffUsers(first: 20) {
            edges {
                node {
                    email
                    isStaff
                }
            }
        }
    }
    """
    variables = {}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffUsers"]["edges"]
    assert len(data) == 2
    staff_emails = [user["node"]["email"] for user in data]
    assert sorted(staff_emails) == [admin_user.email, staff_user.email]
    assert all([user["node"]["isStaff"] for user in data])

    # check permissions
    response = user_api_client.post_graphql(query, variables)
    assert_no_permission(response)


def test_who_can_see_user(
    staff_user, customer_user, staff_api_client, permission_manage_users
):
    query = """
    query Users {
        customers {
            totalCount
        }
    }
    """

    # Random person (even staff) can't see users data without permissions
    ID = graphene.Node.to_global_id("User", customer_user.id)
    variables = {"id": ID}
    response = staff_api_client.post_graphql(USER_QUERY, variables)
    assert_no_permission(response)

    response = staff_api_client.post_graphql(query)
    assert_no_permission(response)

    # Add permission and ensure staff can see user(s)
    staff_user.user_permissions.add(permission_manage_users)
    response = staff_api_client.post_graphql(USER_QUERY, variables)
    content = get_graphql_content(response)
    assert content["data"]["user"]["email"] == customer_user.email

    response = staff_api_client.post_graphql(query)
    content = get_graphql_content(response)
    assert content["data"]["customers"]["totalCount"] == 1


ME_QUERY = """
    query Me {
        me {
            id
            email
            checkout {
                token
            }
            userPermissions {
                code
                name
            }
            checkouts(first: 10) {
                edges {
                    node {
                        id
                    }
                }
                totalCount
            }
        }
    }
"""


def test_me_query(user_api_client):
    response = user_api_client.post_graphql(ME_QUERY)
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert data["email"] == user_api_client.user.email


def test_me_user_permissions_query(
    user_api_client, permission_manage_users, permission_group_manage_users
):
    user = user_api_client.user
    user.user_permissions.add(permission_manage_users)
    user.groups.add(permission_group_manage_users)
    response = user_api_client.post_graphql(ME_QUERY)
    content = get_graphql_content(response)
    user_permissions = content["data"]["me"]["userPermissions"]

    assert len(user_permissions) == 1
    assert user_permissions[0]["code"] == permission_manage_users.codename.upper()


def test_me_query_anonymous_client(api_client):
    response = api_client.post_graphql(ME_QUERY)
    content = get_graphql_content(response)
    assert content["data"]["me"] is None


def test_me_query_customer_can_not_see_note(
    staff_user, staff_api_client, permission_manage_users
):
    query = """
    query Me {
        me {
            id
            email
            note
        }
    }
    """
    # Random person (even staff) can't see own note without permissions
    response = staff_api_client.post_graphql(query)
    assert_no_permission(response)

    # Add permission and ensure staff can see own note
    response = staff_api_client.post_graphql(
        query, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert data["email"] == staff_api_client.user.email
    assert data["note"] == staff_api_client.user.note


def test_me_query_checkout(user_api_client, checkout):
    user = user_api_client.user
    checkout.user = user
    checkout.save()

    response = user_api_client.post_graphql(ME_QUERY)
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert data["checkout"]["token"] == str(checkout.token)
    assert data["checkouts"]["edges"][0]["node"]["id"] == graphene.Node.to_global_id(
        "Checkout", checkout.pk
    )


def test_me_query_checkout_with_inactive_channel(user_api_client, checkout):
    user = user_api_client.user
    channel = checkout.channel
    channel.is_active = False
    channel.save()
    checkout.user = user
    checkout.save()

    response = user_api_client.post_graphql(ME_QUERY)
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert not data["checkout"]
    assert not data["checkouts"]["edges"]


def test_me_query_checkouts_with_channel(user_api_client, checkout, checkout_JPY):
    query = """
        query Me($channel: String) {
            me {
                checkouts(first: 10, channel: $channel) {
                    edges {
                        node {
                            id
                            channel {
                                slug
                            }
                        }
                    }
                    totalCount
                }
            }
        }
    """

    user = user_api_client.user
    checkout.user = checkout_JPY.user = user
    checkout.save()
    checkout_JPY.save()

    response = user_api_client.post_graphql(query, {"channel": checkout.channel.slug})

    content = get_graphql_content(response)
    data = content["data"]["me"]["checkouts"]
    assert data["edges"][0]["node"]["id"] == graphene.Node.to_global_id(
        "Checkout", checkout.pk
    )
    assert data["totalCount"] == 1
    assert data["edges"][0]["node"]["channel"]["slug"] == checkout.channel.slug


QUERY_ME_CHECKOUT_TOKENS = """
query getCheckoutTokens($channel: String) {
  me {
    checkoutTokens(channel: $channel)
  }
}
"""


def test_me_checkout_tokens_without_channel_param(
    user_api_client, checkouts_assigned_to_customer
):
    # given
    checkouts = checkouts_assigned_to_customer

    # when
    response = user_api_client.post_graphql(QUERY_ME_CHECKOUT_TOKENS)

    # then
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert len(data["checkoutTokens"]) == len(checkouts)
    for checkout in checkouts:
        assert str(checkout.token) in data["checkoutTokens"]


def test_me_checkout_tokens_without_channel_param_inactive_channel(
    user_api_client, channel_PLN, checkouts_assigned_to_customer
):
    # given
    channel_PLN.is_active = False
    channel_PLN.save()
    checkouts = checkouts_assigned_to_customer

    # when
    response = user_api_client.post_graphql(QUERY_ME_CHECKOUT_TOKENS)

    # then
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert str(checkouts[0].token) in data["checkoutTokens"]
    assert str(checkouts[1].token) not in data["checkoutTokens"]


def test_me_checkout_tokens_with_channel(
    user_api_client, channel_USD, checkouts_assigned_to_customer
):
    # given
    checkouts = checkouts_assigned_to_customer

    # when
    response = user_api_client.post_graphql(
        QUERY_ME_CHECKOUT_TOKENS, {"channel": channel_USD.slug}
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert str(checkouts[0].token) in data["checkoutTokens"]
    assert str(checkouts[1].token) not in data["checkoutTokens"]


def test_me_checkout_tokens_with_inactive_channel(
    user_api_client, channel_USD, checkouts_assigned_to_customer
):
    # given
    channel_USD.is_active = False
    channel_USD.save()

    # when
    response = user_api_client.post_graphql(
        QUERY_ME_CHECKOUT_TOKENS, {"channel": channel_USD.slug}
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert not data["checkoutTokens"]


def test_me_checkout_tokens_with_not_existing_channel(
    user_api_client, checkouts_assigned_to_customer
):
    # given

    # when
    response = user_api_client.post_graphql(
        QUERY_ME_CHECKOUT_TOKENS, {"channel": "Not-existing"}
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["me"]
    assert not data["checkoutTokens"]


def test_me_with_cancelled_fulfillments(
    user_api_client, fulfilled_order_with_cancelled_fulfillment
):
    query = """
    query Me {
        me {
            orders (first: 1) {
                edges {
                    node {
                        id
                        fulfillments {
                            status
                        }
                    }
                }
            }
        }
    }
    """
    response = user_api_client.post_graphql(query)
    content = get_graphql_content(response)
    order_id = graphene.Node.to_global_id(
        "Order", fulfilled_order_with_cancelled_fulfillment.id
    )
    data = content["data"]["me"]
    order = data["orders"]["edges"][0]["node"]
    assert order["id"] == order_id
    fulfillments = order["fulfillments"]
    assert len(fulfillments) == 1
    assert fulfillments[0]["status"] == FulfillmentStatus.FULFILLED.upper()


def test_user_with_cancelled_fulfillments(
    staff_api_client,
    customer_user,
    permission_manage_users,
    permission_manage_orders,
    fulfilled_order_with_cancelled_fulfillment,
):
    query = """
    query User($id: ID!) {
        user(id: $id) {
            orders (first: 1) {
                edges {
                    node {
                        id
                        fulfillments {
                            status
                        }
                    }
                }
            }
        }
    }
    """
    user_id = graphene.Node.to_global_id("User", customer_user.id)
    variables = {"id": user_id}
    staff_api_client.user.user_permissions.add(
        permission_manage_users, permission_manage_orders
    )
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    order_id = graphene.Node.to_global_id(
        "Order", fulfilled_order_with_cancelled_fulfillment.id
    )
    data = content["data"]["user"]
    order = data["orders"]["edges"][0]["node"]
    assert order["id"] == order_id
    fulfillments = order["fulfillments"]
    assert len(fulfillments) == 2
    assert fulfillments[0]["status"] == FulfillmentStatus.FULFILLED.upper()
    assert fulfillments[1]["status"] == FulfillmentStatus.CANCELED.upper()


ACCOUNT_REGISTER_MUTATION = """
    mutation RegisterAccount(
        $password: String!,
        $email: String!,
        $firstName: String,
        $lastName: String,
        $redirectUrl: String,
        $languageCode: LanguageCodeEnum
        $metadata: [MetadataInput!],
        $channel: String
    ) {
        accountRegister(
            input: {
                password: $password,
                email: $email,
                firstName: $firstName,
                lastName: $lastName,
                redirectUrl: $redirectUrl,
                languageCode: $languageCode,
                metadata: $metadata,
                channel: $channel
            }
        ) {
            errors {
                field
                message
                code
            }
            user {
                id
                email
            }
        }
    }
"""


@override_settings(
    ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=True, ALLOWED_CLIENT_HOSTS=["localhost"]
)
@patch("saleor.account.notifications.default_token_generator.make_token")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register(
    mocked_notify,
    mocked_generator,
    api_client,
    channel_PLN,
    order,
    site_settings,
):
    mocked_generator.return_value = "token"
    email = "customer@example.com"

    redirect_url = "http://localhost:3000"
    variables = {
        "email": email,
        "password": "Password",
        "redirectUrl": redirect_url,
        "firstName": "saleor",
        "lastName": "rocks",
        "languageCode": "PL",
        "metadata": [{"key": "meta", "value": "data"}],
        "channel": channel_PLN.slug,
    }
    query = ACCOUNT_REGISTER_MUTATION
    mutation_name = "accountRegister"

    response = api_client.post_graphql(query, variables)

    new_user = User.objects.get(email=email)
    content = get_graphql_content(response)
    data = content["data"][mutation_name]
    params = urlencode({"email": email, "token": "token"})
    confirm_url = prepare_url(params, redirect_url)

    expected_payload = {
        "user": get_default_user_payload(new_user),
        "token": "token",
        "confirm_url": confirm_url,
        "recipient_email": new_user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }
    assert new_user.metadata == {"meta": "data"}
    assert new_user.language_code == "pl"
    assert new_user.first_name == variables["firstName"]
    assert new_user.last_name == variables["lastName"]
    assert new_user.search_document == generate_user_fields_search_document_value(
        new_user
    )
    assert not data["errors"]
    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_CONFIRMATION,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )

    response = api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"][mutation_name]
    assert data["errors"]
    assert data["errors"][0]["field"] == "email"
    assert data["errors"][0]["code"] == AccountErrorCode.UNIQUE.name

    customer_creation_event = account_events.CustomerEvent.objects.get()
    assert customer_creation_event.type == account_events.CustomerEvents.ACCOUNT_CREATED
    assert customer_creation_event.user == new_user


@override_settings(ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=False)
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register_disabled_email_confirmation(mocked_notify, api_client):
    email = "customer@example.com"
    variables = {"email": email, "password": "Password"}
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    errors = response.json()["data"]["accountRegister"]["errors"]

    assert errors == []
    created_user = User.objects.get()
    expected_payload = get_default_user_payload(created_user)
    expected_payload["token"] = "token"
    expected_payload["redirect_url"] = "http://localhost:3000"
    mocked_notify.assert_not_called()


@override_settings(ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=True)
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register_no_redirect_url(mocked_notify, api_client):
    variables = {"email": "customer@example.com", "password": "Password"}
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    errors = response.json()["data"]["accountRegister"]["errors"]
    assert "redirectUrl" in map(lambda error: error["field"], errors)
    mocked_notify.assert_not_called()


@override_settings(ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=False)
def test_customer_register_upper_case_email(api_client):
    # given
    email = "CUSTOMER@example.com"
    variables = {"email": email, "password": "Password"}

    # when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    content = get_graphql_content(response)

    # then
    data = content["data"]["accountRegister"]
    assert not data["errors"]
    assert data["user"]["email"].lower()


CUSTOMER_CREATE_MUTATION = """
    mutation CreateCustomer(
        $email: String, $firstName: String, $lastName: String, $channel: String
        $note: String, $billing: AddressInput, $shipping: AddressInput,
        $redirect_url: String, $languageCode: LanguageCodeEnum,
        $externalReference: String
    ) {
        customerCreate(input: {
            email: $email,
            firstName: $firstName,
            lastName: $lastName,
            note: $note,
            defaultShippingAddress: $shipping,
            defaultBillingAddress: $billing,
            redirectUrl: $redirect_url,
            languageCode: $languageCode,
            channel: $channel,
            externalReference: $externalReference
        }) {
            errors {
                field
                code
                message
            }
            user {
                id
                defaultBillingAddress {
                    id
                }
                defaultShippingAddress {
                    id
                }
                languageCode
                email
                firstName
                lastName
                isActive
                isStaff
                note
                externalReference
            }
        }
    }
"""


@patch("saleor.account.notifications.default_token_generator.make_token")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_create(
    mocked_notify,
    mocked_generator,
    staff_api_client,
    address,
    permission_manage_users,
    channel_PLN,
    site_settings,
):
    mocked_generator.return_value = "token"
    email = "api_user@example.com"
    first_name = "api_first_name"
    last_name = "api_last_name"
    note = "Test user"
    address_data = convert_dict_keys_to_camel_case(address.as_data())
    address_data.pop("metadata")
    address_data.pop("privateMetadata")

    redirect_url = "https://www.example.com"
    external_reference = "test-ext-ref"
    variables = {
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "note": note,
        "shipping": address_data,
        "billing": address_data,
        "redirect_url": redirect_url,
        "languageCode": "PL",
        "channel": channel_PLN.slug,
        "externalReference": external_reference,
    }

    response = staff_api_client.post_graphql(
        CUSTOMER_CREATE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    new_customer = User.objects.get(email=email)

    shipping_address, billing_address = (
        new_customer.default_shipping_address,
        new_customer.default_billing_address,
    )
    assert shipping_address == address
    assert billing_address == address
    assert shipping_address.pk != billing_address.pk

    data = content["data"]["customerCreate"]
    assert data["errors"] == []
    assert data["user"]["email"] == email
    assert data["user"]["firstName"] == first_name
    assert data["user"]["lastName"] == last_name
    assert data["user"]["note"] == note
    assert data["user"]["languageCode"] == "PL"
    assert data["user"]["externalReference"] == external_reference
    assert not data["user"]["isStaff"]
    assert data["user"]["isActive"]

    new_user = User.objects.get(email=email)
    assert (
        generate_user_fields_search_document_value(new_user) in new_user.search_document
    )
    assert generate_address_search_document_value(address) in new_user.search_document
    params = urlencode({"email": new_user.email, "token": "token"})
    password_set_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(new_user),
        "token": "token",
        "password_set_url": password_set_url,
        "recipient_email": new_user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }
    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_SET_CUSTOMER_PASSWORD,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )

    assert set([shipping_address, billing_address]) == set(new_user.addresses.all())
    customer_creation_event = account_events.CustomerEvent.objects.get()
    assert customer_creation_event.type == account_events.CustomerEvents.ACCOUNT_CREATED
    assert customer_creation_event.user == new_customer


@patch("saleor.account.notifications.default_token_generator.make_token")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_create_send_password_with_url(
    mocked_notify,
    mocked_generator,
    staff_api_client,
    permission_manage_users,
    channel_PLN,
    site_settings,
):
    mocked_generator.return_value = "token"
    email = "api_user@example.com"
    variables = {
        "email": email,
        "redirect_url": "https://www.example.com",
        "channel": channel_PLN.slug,
    }

    response = staff_api_client.post_graphql(
        CUSTOMER_CREATE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["customerCreate"]
    assert not data["errors"]

    new_customer = User.objects.get(email=email)
    assert new_customer
    redirect_url = "https://www.example.com"
    params = urlencode({"email": email, "token": "token"})
    password_set_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(new_customer),
        "password_set_url": password_set_url,
        "token": "token",
        "recipient_email": new_customer.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }
    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_SET_CUSTOMER_PASSWORD,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )


def test_customer_create_without_send_password(
    staff_api_client, permission_manage_users
):
    email = "api_user@example.com"
    variables = {"email": email}
    response = staff_api_client.post_graphql(
        CUSTOMER_CREATE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["customerCreate"]
    assert not data["errors"]
    User.objects.get(email=email)


def test_customer_create_with_invalid_url(staff_api_client, permission_manage_users):
    email = "api_user@example.com"
    variables = {"email": email, "redirect_url": "invalid"}
    response = staff_api_client.post_graphql(
        CUSTOMER_CREATE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["customerCreate"]
    assert data["errors"][0] == {
        "field": "redirectUrl",
        "code": AccountErrorCode.INVALID.name,
        "message": ANY,
    }
    staff_user = User.objects.filter(email=email)
    assert not staff_user


def test_customer_create_with_not_allowed_url(
    staff_api_client, permission_manage_users
):
    email = "api_user@example.com"
    variables = {"email": email, "redirect_url": "https://www.fake.com"}
    response = staff_api_client.post_graphql(
        CUSTOMER_CREATE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["customerCreate"]
    assert data["errors"][0] == {
        "field": "redirectUrl",
        "code": AccountErrorCode.INVALID.name,
        "message": ANY,
    }
    staff_user = User.objects.filter(email=email)
    assert not staff_user


def test_customer_create_with_upper_case_email(
    staff_api_client, permission_manage_users
):
    # given
    email = "UPPERCASE@example.com"
    variables = {"email": email}

    # when
    response = staff_api_client.post_graphql(
        CUSTOMER_CREATE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["customerCreate"]
    assert not data["errors"]
    assert data["user"]["email"] == email.lower()


def test_customer_create_with_non_unique_external_reference(
    staff_api_client, permission_manage_users, customer_user
):
    # given
    ext_ref = "test-ext-ref"
    customer_user.external_reference = ext_ref
    customer_user.save(update_fields=["external_reference"])

    variables = {"email": "mail.test@exampale.com", "externalReference": ext_ref}

    # when
    response = staff_api_client.post_graphql(
        CUSTOMER_CREATE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    error = content["data"]["customerCreate"]["errors"][0]
    assert error["field"] == "externalReference"
    assert error["code"] == AccountErrorCode.UNIQUE.name
    assert error["message"] == "User with this External reference already exists."


def test_customer_update(
    staff_api_client, staff_user, customer_user, address, permission_manage_users
):
    query = """
    mutation UpdateCustomer(
            $id: ID!, $firstName: String, $lastName: String,
            $isActive: Boolean, $note: String, $billing: AddressInput,
            $shipping: AddressInput, $languageCode: LanguageCodeEnum,
            $externalReference: String
        ) {
        customerUpdate(
            id: $id,
            input: {
                isActive: $isActive,
                firstName: $firstName,
                lastName: $lastName,
                note: $note,
                defaultBillingAddress: $billing
                defaultShippingAddress: $shipping,
                languageCode: $languageCode,
                externalReference: $externalReference
                }
            ) {
            errors {
                field
                message
            }
            user {
                id
                firstName
                lastName
                defaultBillingAddress {
                    id
                }
                defaultShippingAddress {
                    id
                }
                languageCode
                isActive
                note
                externalReference
            }
        }
    }
    """

    # this test requires addresses to be set and checks whether new address
    # instances weren't created, but the existing ones got updated
    assert customer_user.default_billing_address
    assert customer_user.default_shipping_address
    billing_address_pk = customer_user.default_billing_address.pk
    shipping_address_pk = customer_user.default_shipping_address.pk

    user_id = graphene.Node.to_global_id("User", customer_user.id)
    first_name = "new_first_name"
    last_name = "new_last_name"
    note = "Test update note"
    external_reference = "test-ext-ref"
    address_data = convert_dict_keys_to_camel_case(address.as_data())
    address_data.pop("metadata")
    address_data.pop("privateMetadata")

    new_street_address = "Updated street address"
    address_data["streetAddress1"] = new_street_address

    variables = {
        "id": user_id,
        "firstName": first_name,
        "lastName": last_name,
        "isActive": False,
        "note": note,
        "billing": address_data,
        "shipping": address_data,
        "languageCode": "PL",
        "externalReference": external_reference,
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    customer = User.objects.get(email=customer_user.email)

    # check that existing instances are updated
    shipping_address, billing_address = (
        customer.default_shipping_address,
        customer.default_billing_address,
    )
    assert billing_address.pk == billing_address_pk
    assert shipping_address.pk == shipping_address_pk

    assert billing_address.street_address_1 == new_street_address
    assert shipping_address.street_address_1 == new_street_address

    data = content["data"]["customerUpdate"]
    assert data["errors"] == []
    assert data["user"]["firstName"] == first_name
    assert data["user"]["lastName"] == last_name
    assert data["user"]["note"] == note
    assert data["user"]["languageCode"] == "PL"
    assert data["user"]["externalReference"] == external_reference
    assert not data["user"]["isActive"]

    (
        name_changed_event,
        deactivated_event,
    ) = account_events.CustomerEvent.objects.order_by("pk")

    assert name_changed_event.type == account_events.CustomerEvents.NAME_ASSIGNED
    assert name_changed_event.user.pk == staff_user.pk
    assert name_changed_event.parameters == {"message": customer.get_full_name()}

    assert deactivated_event.type == account_events.CustomerEvents.ACCOUNT_DEACTIVATED
    assert deactivated_event.user.pk == staff_user.pk
    assert deactivated_event.parameters == {"account_id": customer_user.id}

    customer_user.refresh_from_db()
    assert (
        generate_address_search_document_value(billing_address)
        in customer_user.search_document
    )
    assert (
        generate_address_search_document_value(shipping_address)
        in customer_user.search_document
    )


UPDATE_CUSTOMER_BY_EXTERNAL_REFERENCE = """
    mutation UpdateCustomer(
        $id: ID, $externalReference: String, $input: CustomerInput!
    ) {
        customerUpdate(id: $id, externalReference: $externalReference, input: $input) {
            errors {
                field
                message
                code
            }
            user {
                id
                externalReference
                firstName
            }
        }
    }
    """


def test_customer_update_by_external_reference(
    staff_api_client, customer_user, permission_manage_users
):
    # given
    query = UPDATE_CUSTOMER_BY_EXTERNAL_REFERENCE
    user = customer_user
    new_name = "updated name"
    ext_ref = "test-ext-ref"
    user.external_reference = ext_ref
    user.save(update_fields=["external_reference"])

    variables = {
        "externalReference": ext_ref,
        "input": {"firstName": new_name},
    }

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    user.refresh_from_db()
    data = content["data"]["customerUpdate"]
    assert not data["errors"]
    assert data["user"]["firstName"] == new_name == user.first_name
    assert data["user"]["id"] == graphene.Node.to_global_id("User", user.id)
    assert data["user"]["externalReference"] == ext_ref


def test_update_customer_by_both_id_and_external_reference(
    staff_api_client, customer_user, permission_manage_users
):
    # given
    query = UPDATE_CUSTOMER_BY_EXTERNAL_REFERENCE
    variables = {"input": {}, "externalReference": "whatever", "id": "whatever"}

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["customerUpdate"]
    assert not data["user"]
    assert (
        data["errors"][0]["message"]
        == "Argument 'id' cannot be combined with 'external_reference'"
    )


def test_update_customer_by_external_reference_not_existing(
    staff_api_client, customer_user, permission_manage_users
):
    # given
    query = UPDATE_CUSTOMER_BY_EXTERNAL_REFERENCE
    ext_ref = "non-existing-ext-ref"
    variables = {
        "input": {},
        "externalReference": ext_ref,
    }

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["customerUpdate"]
    assert not data["user"]
    assert data["errors"][0]["message"] == f"Couldn't resolve to a node: {ext_ref}"
    assert data["errors"][0]["field"] == "externalReference"


def test_update_customer_with_non_unique_external_reference(
    staff_api_client, permission_manage_users, user_list
):
    # given
    query = UPDATE_CUSTOMER_BY_EXTERNAL_REFERENCE

    ext_ref = "test-ext-ref"
    user_1 = user_list[0]
    user_1.external_reference = ext_ref
    user_1.save(update_fields=["external_reference"])
    user_2_id = graphene.Node.to_global_id("User", user_list[1].id)

    variables = {"input": {"externalReference": ext_ref}, "id": user_2_id}

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    error = content["data"]["customerUpdate"]["errors"][0]
    assert error["field"] == "externalReference"
    assert error["code"] == AccountErrorCode.UNIQUE.name
    assert error["message"] == "User with this External reference already exists."


UPDATE_CUSTOMER_EMAIL_MUTATION = """
    mutation UpdateCustomer(
            $id: ID!, $firstName: String, $lastName: String, $email: String) {
        customerUpdate(id: $id, input: {
            firstName: $firstName,
            lastName: $lastName,
            email: $email
        }) {
            errors {
                field
                message
            }
        }
    }
"""


def test_customer_update_generates_event_when_changing_email(
    staff_api_client, staff_user, customer_user, address, permission_manage_users
):
    query = UPDATE_CUSTOMER_EMAIL_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)
    address_data = convert_dict_keys_to_camel_case(address.as_data())

    new_street_address = "Updated street address"
    address_data["streetAddress1"] = new_street_address

    variables = {
        "id": user_id,
        "firstName": customer_user.first_name,
        "lastName": customer_user.last_name,
        "email": "mirumee@example.com",
    }
    staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )

    # The email was changed, an event should have been triggered
    email_changed_event = account_events.CustomerEvent.objects.get()
    assert email_changed_event.type == account_events.CustomerEvents.EMAIL_ASSIGNED
    assert email_changed_event.user.pk == staff_user.pk
    assert email_changed_event.parameters == {"message": "mirumee@example.com"}


UPDATE_CUSTOMER_IS_ACTIVE_MUTATION = """
    mutation UpdateCustomer(
        $id: ID!, $isActive: Boolean) {
            customerUpdate(id: $id, input: {
            isActive: $isActive,
        }) {
            errors {
                field
                message
            }
        }
    }
"""


def test_customer_update_generates_event_when_deactivating(
    staff_api_client, staff_user, customer_user, address, permission_manage_users
):
    query = UPDATE_CUSTOMER_IS_ACTIVE_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)

    variables = {"id": user_id, "isActive": False}
    staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )

    account_deactivated_event = account_events.CustomerEvent.objects.get()
    assert (
        account_deactivated_event.type
        == account_events.CustomerEvents.ACCOUNT_DEACTIVATED
    )
    assert account_deactivated_event.user.pk == staff_user.pk
    assert account_deactivated_event.parameters == {"account_id": customer_user.id}


def test_customer_update_generates_event_when_activating(
    staff_api_client, staff_user, customer_user, address, permission_manage_users
):
    customer_user.is_active = False
    customer_user.save(update_fields=["is_active"])

    query = UPDATE_CUSTOMER_IS_ACTIVE_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)

    variables = {"id": user_id, "isActive": True}
    staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )

    account_activated_event = account_events.CustomerEvent.objects.get()
    assert (
        account_activated_event.type == account_events.CustomerEvents.ACCOUNT_ACTIVATED
    )
    assert account_activated_event.user.pk == staff_user.pk
    assert account_activated_event.parameters == {"account_id": customer_user.id}


def test_customer_update_generates_event_when_deactivating_as_app(
    app_api_client, staff_user, customer_user, address, permission_manage_users
):
    query = UPDATE_CUSTOMER_IS_ACTIVE_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)

    variables = {"id": user_id, "isActive": False}
    app_api_client.post_graphql(query, variables, permissions=[permission_manage_users])

    account_deactivated_event = account_events.CustomerEvent.objects.get()
    assert (
        account_deactivated_event.type
        == account_events.CustomerEvents.ACCOUNT_DEACTIVATED
    )
    assert account_deactivated_event.user is None
    assert account_deactivated_event.app.pk == app_api_client.app.pk
    assert account_deactivated_event.parameters == {"account_id": customer_user.id}


def test_customer_update_generates_event_when_activating_as_app(
    app_api_client, staff_user, customer_user, address, permission_manage_users
):
    customer_user.is_active = False
    customer_user.save(update_fields=["is_active"])

    query = UPDATE_CUSTOMER_IS_ACTIVE_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)

    variables = {"id": user_id, "isActive": True}
    app_api_client.post_graphql(query, variables, permissions=[permission_manage_users])

    account_activated_event = account_events.CustomerEvent.objects.get()
    assert (
        account_activated_event.type == account_events.CustomerEvents.ACCOUNT_ACTIVATED
    )
    assert account_activated_event.user is None
    assert account_activated_event.app.pk == app_api_client.app.pk
    assert account_activated_event.parameters == {"account_id": customer_user.id}


def test_customer_update_without_any_changes_generates_no_event(
    staff_api_client, customer_user, address, permission_manage_users
):
    query = UPDATE_CUSTOMER_EMAIL_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)
    address_data = convert_dict_keys_to_camel_case(address.as_data())

    new_street_address = "Updated street address"
    address_data["streetAddress1"] = new_street_address

    variables = {
        "id": user_id,
        "firstName": customer_user.first_name,
        "lastName": customer_user.last_name,
        "email": customer_user.email,
    }
    staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )

    # No event should have been generated
    assert not account_events.CustomerEvent.objects.exists()


def test_customer_update_generates_event_when_changing_email_by_app(
    app_api_client, staff_user, customer_user, address, permission_manage_users
):
    query = UPDATE_CUSTOMER_EMAIL_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)
    address_data = convert_dict_keys_to_camel_case(address.as_data())

    new_street_address = "Updated street address"
    address_data["streetAddress1"] = new_street_address

    variables = {
        "id": user_id,
        "firstName": customer_user.first_name,
        "lastName": customer_user.last_name,
        "email": "mirumee@example.com",
    }
    app_api_client.post_graphql(query, variables, permissions=[permission_manage_users])

    # The email was changed, an event should have been triggered
    email_changed_event = account_events.CustomerEvent.objects.get()
    assert email_changed_event.type == account_events.CustomerEvents.EMAIL_ASSIGNED
    assert email_changed_event.user is None
    assert email_changed_event.parameters == {"message": "mirumee@example.com"}


def test_customer_update_assign_gift_cards_and_orders(
    staff_api_client,
    staff_user,
    customer_user,
    address,
    gift_card,
    order,
    permission_manage_users,
):
    # given
    query = UPDATE_CUSTOMER_EMAIL_MUTATION

    user_id = graphene.Node.to_global_id("User", customer_user.id)
    address_data = convert_dict_keys_to_camel_case(address.as_data())

    new_street_address = "Updated street address"
    address_data["streetAddress1"] = new_street_address
    new_email = "mirumee@example.com"

    gift_card.created_by = None
    gift_card.created_by_email = new_email
    gift_card.save(update_fields=["created_by", "created_by_email"])

    order.user = None
    order.user_email = new_email
    order.save(update_fields=["user_email", "user"])

    variables = {
        "id": user_id,
        "firstName": customer_user.first_name,
        "lastName": customer_user.last_name,
        "email": new_email,
    }

    # when
    staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )

    # then
    email_changed_event = account_events.CustomerEvent.objects.get()
    assert email_changed_event.type == account_events.CustomerEvents.EMAIL_ASSIGNED
    gift_card.refresh_from_db()
    customer_user.refresh_from_db()
    assert gift_card.created_by == customer_user
    assert gift_card.created_by_email == customer_user.email
    order.refresh_from_db()
    assert order.user == customer_user


ACCOUNT_UPDATE_QUERY = """
    mutation accountUpdate(
        $billing: AddressInput
        $shipping: AddressInput
        $firstName: String,
        $lastName: String
        $languageCode: LanguageCodeEnum
    ) {
        accountUpdate(
          input: {
            defaultBillingAddress: $billing,
            defaultShippingAddress: $shipping,
            firstName: $firstName,
            lastName: $lastName,
            languageCode: $languageCode
        }) {
            errors {
                field
                code
                message
                addressType
            }
            user {
                firstName
                lastName
                email
                defaultBillingAddress {
                    id
                }
                defaultShippingAddress {
                    id
                }
                languageCode
            }
        }
    }
"""


def test_logged_customer_updates_language_code(user_api_client):
    language_code = "PL"
    user = user_api_client.user
    assert user.language_code != language_code
    variables = {"languageCode": language_code}

    response = user_api_client.post_graphql(ACCOUNT_UPDATE_QUERY, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountUpdate"]

    assert not data["errors"]
    assert data["user"]["languageCode"] == language_code
    user.refresh_from_db()
    assert user.language_code == language_code.lower()
    assert user.search_document


def test_logged_customer_update_names(user_api_client):
    first_name = "first"
    last_name = "last"
    user = user_api_client.user
    assert user.first_name != first_name
    assert user.last_name != last_name

    variables = {"firstName": first_name, "lastName": last_name}
    response = user_api_client.post_graphql(ACCOUNT_UPDATE_QUERY, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountUpdate"]

    user.refresh_from_db()
    assert not data["errors"]
    assert user.first_name == first_name
    assert user.last_name == last_name


def test_logged_customer_update_addresses(user_api_client, graphql_address_data):
    # this test requires addresses to be set and checks whether new address
    # instances weren't created, but the existing ones got updated
    user = user_api_client.user
    new_first_name = graphql_address_data["firstName"]
    assert user.default_billing_address
    assert user.default_shipping_address
    assert user.default_billing_address.first_name != new_first_name
    assert user.default_shipping_address.first_name != new_first_name

    query = ACCOUNT_UPDATE_QUERY
    mutation_name = "accountUpdate"
    variables = {"billing": graphql_address_data, "shipping": graphql_address_data}
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"][mutation_name]
    assert not data["errors"]

    # check that existing instances are updated
    billing_address_pk = user.default_billing_address.pk
    shipping_address_pk = user.default_shipping_address.pk
    user = User.objects.get(email=user.email)
    assert user.default_billing_address.pk == billing_address_pk
    assert user.default_shipping_address.pk == shipping_address_pk

    assert user.default_billing_address.first_name == new_first_name
    assert user.default_shipping_address.first_name == new_first_name
    assert user.search_document


def test_logged_customer_update_addresses_invalid_shipping_address(
    user_api_client, graphql_address_data
):
    shipping_address = graphql_address_data.copy()
    del shipping_address["country"]

    query = ACCOUNT_UPDATE_QUERY
    mutation_name = "accountUpdate"
    variables = {"billing": graphql_address_data, "shipping": shipping_address}
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"][mutation_name]
    assert len(data["errors"]) == 1
    errors = data["errors"]
    assert errors[0]["field"] == "country"
    assert errors[0]["code"] == AccountErrorCode.REQUIRED.name
    assert errors[0]["addressType"] == AddressType.SHIPPING.upper()


def test_logged_customer_update_addresses_invalid_billing_address(
    user_api_client, graphql_address_data
):
    billing_address = graphql_address_data.copy()
    del billing_address["country"]

    query = ACCOUNT_UPDATE_QUERY
    mutation_name = "accountUpdate"
    variables = {"billing": billing_address, "shipping": graphql_address_data}
    response = user_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"][mutation_name]
    assert len(data["errors"]) == 1
    errors = data["errors"]
    assert errors[0]["field"] == "country"
    assert errors[0]["code"] == AccountErrorCode.REQUIRED.name
    assert errors[0]["addressType"] == AddressType.BILLING.upper()


def test_logged_customer_update_anonymous_user(api_client):
    query = ACCOUNT_UPDATE_QUERY
    response = api_client.post_graphql(query, {})
    assert_no_permission(response)


ACCOUNT_REQUEST_DELETION_MUTATION = """
    mutation accountRequestDeletion($redirectUrl: String!, $channel: String) {
        accountRequestDeletion(redirectUrl: $redirectUrl, channel: $channel) {
            errors {
                field
                code
                message
            }
        }
    }
"""


@patch("saleor.account.notifications.account_delete_token_generator.make_token")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_account_request_deletion(
    mocked_notify, mocked_token, user_api_client, channel_PLN, site_settings
):
    mocked_token.return_value = "token"
    user = user_api_client.user
    redirect_url = "https://www.example.com"
    variables = {"redirectUrl": redirect_url, "channel": channel_PLN.slug}
    response = user_api_client.post_graphql(
        ACCOUNT_REQUEST_DELETION_MUTATION, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["accountRequestDeletion"]
    assert not data["errors"]
    params = urlencode({"token": "token"})
    delete_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(user),
        "delete_url": delete_url,
        "token": "token",
        "recipient_email": user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }

    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_DELETE,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_account_request_deletion_token_validation(
    mocked_notify, user_api_client, channel_PLN, site_settings
):
    user = user_api_client.user
    token = account_delete_token_generator.make_token(user)
    redirect_url = "https://www.example.com"
    variables = {"redirectUrl": redirect_url, "channel": channel_PLN.slug}
    response = user_api_client.post_graphql(
        ACCOUNT_REQUEST_DELETION_MUTATION, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["accountRequestDeletion"]
    assert not data["errors"]
    params = urlencode({"token": token})
    delete_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(user),
        "delete_url": delete_url,
        "token": token,
        "recipient_email": user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }

    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_DELETE,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )


@patch("saleor.plugins.manager.PluginsManager.notify")
def test_account_request_deletion_anonymous_user(mocked_notify, api_client):
    variables = {"redirectUrl": "https://www.example.com"}
    response = api_client.post_graphql(ACCOUNT_REQUEST_DELETION_MUTATION, variables)
    assert_no_permission(response)
    mocked_notify.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.notify")
def test_account_request_deletion_storefront_hosts_not_allowed(
    mocked_notify, user_api_client
):
    variables = {"redirectUrl": "https://www.fake.com"}
    response = user_api_client.post_graphql(
        ACCOUNT_REQUEST_DELETION_MUTATION, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["accountRequestDeletion"]
    assert len(data["errors"]) == 1
    assert data["errors"][0] == {
        "field": "redirectUrl",
        "code": AccountErrorCode.INVALID.name,
        "message": ANY,
    }
    mocked_notify.assert_not_called()


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_account_request_deletion_all_storefront_hosts_allowed(
    mocked_notify, user_api_client, settings, channel_PLN, site_settings
):
    user = user_api_client.user
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    token = account_delete_token_generator.make_token(user)
    settings.ALLOWED_CLIENT_HOSTS = ["*"]
    redirect_url = "https://www.test.com"
    variables = {"redirectUrl": redirect_url, "channel": channel_PLN.slug}
    response = user_api_client.post_graphql(
        ACCOUNT_REQUEST_DELETION_MUTATION, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["accountRequestDeletion"]
    assert not data["errors"]

    params = urlencode({"token": token})
    delete_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(user),
        "delete_url": delete_url,
        "token": token,
        "recipient_email": user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }

    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_DELETE,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_account_request_deletion_subdomain(
    mocked_notify, user_api_client, settings, channel_PLN, site_settings
):
    user = user_api_client.user
    token = account_delete_token_generator.make_token(user)
    settings.ALLOWED_CLIENT_HOSTS = [".example.com"]
    redirect_url = "https://sub.example.com"
    variables = {"redirectUrl": redirect_url, "channel": channel_PLN.slug}
    response = user_api_client.post_graphql(
        ACCOUNT_REQUEST_DELETION_MUTATION, variables
    )
    content = get_graphql_content(response)
    data = content["data"]["accountRequestDeletion"]
    assert not data["errors"]
    params = urlencode({"token": token})
    delete_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(user),
        "delete_url": delete_url,
        "token": token,
        "recipient_email": user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }

    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_DELETE,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )


ACCOUNT_DELETE_MUTATION = """
    mutation AccountDelete($token: String!){
        accountDelete(token: $token){
            errors{
                field
                message
            }
        }
    }
"""


@patch("saleor.core.tasks.delete_from_storage_task.delay")
@freeze_time("2018-05-31 12:00:01")
def test_account_delete(delete_from_storage_task_mock, user_api_client, media_root):
    # given
    thumbnail_mock = MagicMock(spec=File)
    thumbnail_mock.name = "image.jpg"

    user = user_api_client.user
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    user_id = user.id

    # create thumbnail
    thumbnail = Thumbnail.objects.create(user=user, size=128, image=thumbnail_mock)
    assert user.thumbnails.all()
    img_path = thumbnail.image.name

    token = account_delete_token_generator.make_token(user)
    variables = {"token": token}

    # when
    response = user_api_client.post_graphql(ACCOUNT_DELETE_MUTATION, variables)

    # then
    content = get_graphql_content(response)
    data = content["data"]["accountDelete"]
    assert not data["errors"]
    assert not User.objects.filter(pk=user.id).exists()
    # ensure all related thumbnails have been deleted
    assert not Thumbnail.objects.filter(user_id=user_id).exists()
    delete_from_storage_task_mock.assert_called_once_with(img_path)


@freeze_time("2018-05-31 12:00:01")
def test_account_delete_user_never_log_in(user_api_client):
    user = user_api_client.user
    token = account_delete_token_generator.make_token(user)
    variables = {"token": token}

    response = user_api_client.post_graphql(ACCOUNT_DELETE_MUTATION, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountDelete"]
    assert not data["errors"]
    assert not User.objects.filter(pk=user.id).exists()


@freeze_time("2018-05-31 12:00:01")
def test_account_delete_log_out_after_deletion_request(user_api_client):
    user = user_api_client.user
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    token = account_delete_token_generator.make_token(user)

    # simulate re-login
    user.last_login = timezone.now() + datetime.timedelta(hours=1)
    user.save(update_fields=["last_login"])

    variables = {"token": token}

    response = user_api_client.post_graphql(ACCOUNT_DELETE_MUTATION, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountDelete"]
    assert not data["errors"]
    assert not User.objects.filter(pk=user.id).exists()


def test_account_delete_invalid_token(user_api_client):
    user = user_api_client.user
    variables = {"token": "invalid"}

    response = user_api_client.post_graphql(ACCOUNT_DELETE_MUTATION, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountDelete"]
    assert len(data["errors"]) == 1
    assert data["errors"][0]["message"] == "Invalid or expired token."
    assert User.objects.filter(pk=user.id).exists()


def test_account_delete_anonymous_user(api_client):
    variables = {"token": "invalid"}

    response = api_client.post_graphql(ACCOUNT_DELETE_MUTATION, variables)
    assert_no_permission(response)


def test_account_delete_staff_user(staff_api_client):
    user = staff_api_client.user
    variables = {"token": "invalid"}

    response = staff_api_client.post_graphql(ACCOUNT_DELETE_MUTATION, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountDelete"]
    assert len(data["errors"]) == 1
    assert data["errors"][0]["message"] == "Cannot delete a staff account."
    assert User.objects.filter(pk=user.id).exists()


@freeze_time("2018-05-31 12:00:01")
def test_account_delete_other_customer_token(user_api_client):
    user = user_api_client.user
    other_user = User.objects.create(email="temp@example.com")
    token = account_delete_token_generator.make_token(other_user)
    variables = {"token": token}

    response = user_api_client.post_graphql(ACCOUNT_DELETE_MUTATION, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountDelete"]
    assert len(data["errors"]) == 1
    assert data["errors"][0]["message"] == "Invalid or expired token."
    assert User.objects.filter(pk=user.id).exists()
    assert User.objects.filter(pk=other_user.id).exists()


CUSTOMER_DELETE_MUTATION = """
    mutation CustomerDelete($id: ID, $externalReference: String) {
        customerDelete(id: $id, externalReference: $externalReference) {
            errors {
                field
                message
            }
            user {
                id
                externalReference
            }
        }
    }
"""


@patch("saleor.account.signals.delete_from_storage_task.delay")
@patch("saleor.graphql.account.utils.account_events.customer_deleted_event")
def test_customer_delete(
    mocked_deletion_event,
    delete_from_storage_task_mock,
    staff_api_client,
    staff_user,
    customer_user,
    image,
    permission_manage_users,
    media_root,
):
    """Ensure deleting a customer actually deletes the customer and creates proper
    related events"""

    query = CUSTOMER_DELETE_MUTATION
    customer_id = graphene.Node.to_global_id("User", customer_user.pk)
    customer_user.avatar = image
    customer_user.save(update_fields=["avatar"])
    variables = {"id": customer_id}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["customerDelete"]
    assert data["errors"] == []
    assert data["user"]["id"] == customer_id

    # Ensure the customer was properly deleted
    # and any related event was properly triggered
    mocked_deletion_event.assert_called_once_with(
        staff_user=staff_user, app=None, deleted_count=1
    )
    delete_from_storage_task_mock.assert_called_once_with(customer_user.avatar.name)


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_customer_delete_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_api_client,
    customer_user,
    permission_manage_users,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    customer_id = graphene.Node.to_global_id("User", customer_user.pk)
    variables = {"id": customer_id}

    # when
    response = staff_api_client.post_graphql(
        CUSTOMER_DELETE_MUTATION, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["customerDelete"]

    # then
    assert data["errors"] == []
    assert data["user"]["id"] == customer_id
    mocked_webhook_trigger.assert_called_once_with(
        generate_customer_payload(customer_user, staff_api_client.user),
        WebhookEventAsyncType.CUSTOMER_DELETED,
        [any_webhook],
        customer_user,
        SimpleLazyObject(lambda: staff_api_client.user),
    )


@patch("saleor.account.signals.delete_from_storage_task.delay")
@patch("saleor.graphql.account.utils.account_events.customer_deleted_event")
def test_customer_delete_by_app(
    mocked_deletion_event,
    delete_from_storage_task_mock,
    app_api_client,
    app,
    customer_user,
    image,
    permission_manage_users,
    media_root,
):
    """Ensure deleting a customer actually deletes the customer and creates proper
    related events"""

    query = CUSTOMER_DELETE_MUTATION
    customer_id = graphene.Node.to_global_id("User", customer_user.pk)
    customer_user.avatar = image
    customer_user.save(update_fields=["avatar"])
    variables = {"id": customer_id}
    response = app_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)
    data = content["data"]["customerDelete"]
    assert data["errors"] == []
    assert data["user"]["id"] == customer_id

    # Ensure the customer was properly deleted
    # and any related event was properly triggered
    assert mocked_deletion_event.call_count == 1
    args, kwargs = mocked_deletion_event.call_args
    assert kwargs["deleted_count"] == 1
    assert kwargs["staff_user"] is None
    assert kwargs["app"] == app
    delete_from_storage_task_mock.assert_called_once_with(customer_user.avatar.name)


def test_customer_delete_errors(customer_user, admin_user, staff_user):
    info = Mock(context=Mock(user=admin_user))
    with pytest.raises(ValidationError) as e:
        CustomerDelete.clean_instance(info, staff_user)

    msg = "Cannot delete a staff account."
    assert e.value.error_dict["id"][0].message == msg

    # should not raise any errors
    CustomerDelete.clean_instance(info, customer_user)


def test_customer_delete_by_external_reference(
    staff_api_client, customer_user, permission_manage_users
):
    # given
    user = customer_user
    query = CUSTOMER_DELETE_MUTATION
    ext_ref = "test-ext-ref"
    user.external_reference = ext_ref
    user.save(update_fields=["external_reference"])
    variables = {"externalReference": ext_ref}

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["customerDelete"]
    with pytest.raises(user._meta.model.DoesNotExist):
        user.refresh_from_db()
    assert not data["errors"]
    assert data["user"]["externalReference"] == ext_ref
    assert data["user"]["id"] == graphene.Node.to_global_id("User", user.id)


def test_delete_customer_by_both_id_and_external_reference(
    staff_api_client, customer_user, permission_manage_users
):
    # given
    query = CUSTOMER_DELETE_MUTATION
    variables = {"externalReference": "whatever", "id": "whatever"}

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    errors = content["data"]["customerDelete"]["errors"]
    assert (
        errors[0]["message"]
        == "Argument 'id' cannot be combined with 'external_reference'"
    )


def test_delete_customer_by_external_reference_not_existing(
    staff_api_client, customer_user, permission_manage_users
):
    # given
    query = CUSTOMER_DELETE_MUTATION
    ext_ref = "non-existing-ext-ref"
    variables = {"externalReference": ext_ref}

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    # then
    errors = content["data"]["customerDelete"]["errors"]
    assert errors[0]["message"] == f"Couldn't resolve to a node: {ext_ref}"


STAFF_CREATE_MUTATION = """
    mutation CreateStaff(
            $email: String, $redirect_url: String, $add_groups: [ID!]
        ) {
        staffCreate(input: {email: $email, redirectUrl: $redirect_url,
            addGroups: $add_groups}
        ) {
            errors {
                field
                code
                permissions
                groups
            }
            user {
                id
                email
                isStaff
                isActive
                userPermissions {
                    code
                }
                permissionGroups {
                    name
                    permissions {
                        code
                    }
                }
                avatar {
                    url
                }
            }
        }
    }
"""


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_staff_create(
    mocked_notify,
    staff_api_client,
    staff_user,
    media_root,
    permission_group_manage_users,
    permission_manage_products,
    permission_manage_staff,
    permission_manage_users,
    channel_PLN,
    site_settings,
):
    group = permission_group_manage_users
    group.permissions.add(permission_manage_products)
    staff_user.user_permissions.add(permission_manage_products, permission_manage_users)
    email = "api_user@example.com"
    redirect_url = "https://www.example.com"
    variables = {
        "email": email,
        "redirect_url": redirect_url,
        "add_groups": [graphene.Node.to_global_id("Group", group.pk)],
    }

    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    assert data["errors"] == []
    assert data["user"]["email"] == email
    assert data["user"]["isStaff"]
    assert data["user"]["isActive"]

    expected_perms = {
        permission_manage_products.codename,
        permission_manage_users.codename,
    }
    permissions = data["user"]["userPermissions"]
    assert {perm["code"].lower() for perm in permissions} == expected_perms

    staff_user = User.objects.get(email=email)

    assert staff_user.is_staff
    assert staff_user.search_document == f"{email}\n".lower()

    groups = data["user"]["permissionGroups"]
    assert len(groups) == 1
    assert {perm["code"].lower() for perm in groups[0]["permissions"]} == expected_perms

    token = default_token_generator.make_token(staff_user)
    params = urlencode({"email": email, "token": token})
    password_set_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(staff_user),
        "password_set_url": password_set_url,
        "token": token,
        "recipient_email": staff_user.email,
        "channel_slug": None,
        **get_site_context_payload(site_settings.site),
    }

    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_SET_STAFF_PASSWORD,
        payload=expected_payload,
        channel_slug=None,
    )


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_promote_customer_to_staff_user(
    mocked_notify,
    staff_api_client,
    staff_user,
    customer_user,
    media_root,
    permission_group_manage_users,
    permission_manage_products,
    permission_manage_staff,
    permission_manage_users,
    channel_PLN,
):
    group = permission_group_manage_users
    group.permissions.add(permission_manage_products)
    staff_user.user_permissions.add(permission_manage_products, permission_manage_users)
    redirect_url = "https://www.example.com"
    email = customer_user.email
    variables = {
        "email": email,
        "redirect_url": redirect_url,
        "add_groups": [graphene.Node.to_global_id("Group", group.pk)],
    }

    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    assert data["errors"] == []
    assert data["user"]["email"] == email
    assert data["user"]["isStaff"]
    assert data["user"]["isActive"]

    expected_perms = {
        permission_manage_products.codename,
        permission_manage_users.codename,
    }
    permissions = data["user"]["userPermissions"]
    assert {perm["code"].lower() for perm in permissions} == expected_perms

    staff_user = User.objects.get(email=email)

    assert staff_user.is_staff

    groups = data["user"]["permissionGroups"]
    assert len(groups) == 1
    assert {perm["code"].lower() for perm in groups[0]["permissions"]} == expected_perms

    mocked_notify.assert_not_called()


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_staff_create_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_api_client,
    staff_user,
    permission_group_manage_users,
    permission_manage_staff,
    permission_manage_users,
    channel_PLN,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    staff_user.user_permissions.add(permission_manage_users)
    email = "api_user@example.com"
    redirect_url = "https://www.example.com"
    variables = {
        "email": email,
        "redirect_url": redirect_url,
        "add_groups": [
            graphene.Node.to_global_id("Group", permission_group_manage_users.pk)
        ],
    }

    # when
    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    new_staff_user = User.objects.get(email=email)

    # then
    assert not data["errors"]
    assert data["user"]
    expected_call = call(
        json.dumps(
            {
                "id": graphene.Node.to_global_id("User", new_staff_user.id),
                "email": email,
                "meta": generate_meta(
                    requestor_data=generate_requestor(
                        SimpleLazyObject(lambda: staff_api_client.user)
                    )
                ),
            },
            cls=CustomJsonEncoder,
        ),
        WebhookEventAsyncType.STAFF_CREATED,
        [any_webhook],
        new_staff_user,
        SimpleLazyObject(lambda: staff_api_client.user),
    )

    assert expected_call in mocked_webhook_trigger.call_args_list


def test_staff_create_app_no_permission(
    app_api_client,
    staff_user,
    media_root,
    permission_group_manage_users,
    permission_manage_products,
    permission_manage_staff,
    permission_manage_users,
):
    group = permission_group_manage_users
    group.permissions.add(permission_manage_products)
    staff_user.user_permissions.add(permission_manage_products, permission_manage_users)
    email = "api_user@example.com"
    variables = {
        "email": email,
        "redirect_url": "https://www.example.com",
        "add_groups": [graphene.Node.to_global_id("Group", group.pk)],
    }

    response = app_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )

    assert_no_permission(response)


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_staff_create_out_of_scope_group(
    mocked_notify,
    staff_api_client,
    superuser_api_client,
    media_root,
    permission_manage_staff,
    permission_manage_users,
    permission_group_manage_users,
    channel_PLN,
    site_settings,
):
    """Ensure user can't create staff with groups which are out of user scope.
    Ensure superuser pass restrictions.
    """
    group = permission_group_manage_users
    group2 = Group.objects.create(name="second group")
    group2.permissions.add(permission_manage_staff)
    email = "api_user@example.com"
    redirect_url = "https://www.example.com"
    variables = {
        "email": email,
        "redirect_url": redirect_url,
        "add_groups": [
            graphene.Node.to_global_id("Group", gr.pk) for gr in [group, group2]
        ],
    }

    # for staff user
    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    errors = data["errors"]
    assert not data["user"]
    assert len(errors) == 1

    expected_error = {
        "field": "addGroups",
        "code": AccountErrorCode.OUT_OF_SCOPE_GROUP.name,
        "permissions": None,
        "groups": [graphene.Node.to_global_id("Group", group.pk)],
    }

    assert errors[0] == expected_error

    mocked_notify.assert_not_called()

    # for superuser
    response = superuser_api_client.post_graphql(STAFF_CREATE_MUTATION, variables)
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]

    assert data["errors"] == []
    assert data["user"]["email"] == email
    assert data["user"]["isStaff"]
    assert data["user"]["isActive"]
    expected_perms = {
        permission_manage_staff.codename,
        permission_manage_users.codename,
    }
    permissions = data["user"]["userPermissions"]
    assert {perm["code"].lower() for perm in permissions} == expected_perms

    staff_user = User.objects.get(email=email)

    assert staff_user.is_staff

    expected_groups = [
        {
            "name": group.name,
            "permissions": [{"code": permission_manage_users.codename.upper()}],
        },
        {
            "name": group2.name,
            "permissions": [{"code": permission_manage_staff.codename.upper()}],
        },
    ]
    groups = data["user"]["permissionGroups"]
    assert len(groups) == 2
    for group in expected_groups:
        assert group in groups
    token = default_token_generator.make_token(staff_user)
    params = urlencode({"email": email, "token": token})
    password_set_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(staff_user),
        "password_set_url": password_set_url,
        "token": token,
        "recipient_email": staff_user.email,
        "channel_slug": None,
        **get_site_context_payload(site_settings.site),
    }

    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_SET_STAFF_PASSWORD,
        payload=expected_payload,
        channel_slug=None,
    )


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_staff_create_send_password_with_url(
    mocked_notify, staff_api_client, media_root, permission_manage_staff, site_settings
):
    email = "api_user@example.com"
    redirect_url = "https://www.example.com"
    variables = {"email": email, "redirect_url": redirect_url}

    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    assert not data["errors"]

    staff_user = User.objects.get(email=email)
    assert staff_user.is_staff

    token = default_token_generator.make_token(staff_user)
    params = urlencode({"email": email, "token": token})
    password_set_url = prepare_url(params, redirect_url)
    expected_payload = {
        "user": get_default_user_payload(staff_user),
        "password_set_url": password_set_url,
        "token": token,
        "recipient_email": staff_user.email,
        "channel_slug": None,
        **get_site_context_payload(site_settings.site),
    }

    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_SET_STAFF_PASSWORD,
        payload=expected_payload,
        channel_slug=None,
    )


def test_staff_create_without_send_password(
    staff_api_client, media_root, permission_manage_staff
):
    email = "api_user@example.com"
    variables = {"email": email}
    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    assert not data["errors"]
    User.objects.get(email=email)


def test_staff_create_with_invalid_url(
    staff_api_client, media_root, permission_manage_staff
):
    email = "api_user@example.com"
    variables = {"email": email, "redirect_url": "invalid"}
    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    assert data["errors"][0] == {
        "field": "redirectUrl",
        "code": AccountErrorCode.INVALID.name,
        "permissions": None,
        "groups": None,
    }
    staff_user = User.objects.filter(email=email)
    assert not staff_user


def test_staff_create_with_not_allowed_url(
    staff_api_client, media_root, permission_manage_staff
):
    email = "api_userrr@example.com"
    variables = {"email": email, "redirect_url": "https://www.fake.com"}
    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffCreate"]
    assert data["errors"][0] == {
        "field": "redirectUrl",
        "code": AccountErrorCode.INVALID.name,
        "permissions": None,
        "groups": None,
    }
    staff_user = User.objects.filter(email=email)
    assert not staff_user


def test_staff_create_with_upper_case_email(
    staff_api_client, media_root, permission_manage_staff
):
    # given
    email = "api_user@example.com"
    variables = {"email": email}

    # when
    response = staff_api_client.post_graphql(
        STAFF_CREATE_MUTATION, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)

    # then
    data = content["data"]["staffCreate"]
    assert not data["errors"]
    assert data["user"]["email"] == email.lower()


STAFF_UPDATE_MUTATIONS = """
    mutation UpdateStaff(
            $id: ID!, $input: StaffUpdateInput!) {
        staffUpdate(
                id: $id,
                input: $input) {
            errors {
                field
                code
                message
                permissions
                groups
            }
            user {
                userPermissions {
                    code
                }
                permissionGroups {
                    name
                }
                isActive
                email
            }
        }
    }
"""


def test_staff_update(staff_api_client, permission_manage_staff, media_root):
    query = STAFF_UPDATE_MUTATIONS
    staff_user = User.objects.create(email="staffuser@example.com", is_staff=True)
    assert not staff_user.search_document
    id = graphene.Node.to_global_id("User", staff_user.id)
    variables = {"id": id, "input": {"isActive": False}}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )

    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    assert data["errors"] == []
    assert data["user"]["userPermissions"] == []
    assert not data["user"]["isActive"]
    staff_user.refresh_from_db()
    assert not staff_user.search_document


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_staff_update_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_api_client,
    permission_manage_staff,
    media_root,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    staff_user = User.objects.create(email="staffuser@example.com", is_staff=True)
    assert not staff_user.search_document
    id = graphene.Node.to_global_id("User", staff_user.id)
    variables = {"id": id, "input": {"isActive": False}}

    # when
    response = staff_api_client.post_graphql(
        STAFF_UPDATE_MUTATIONS, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]

    # then
    assert not data["errors"]
    assert data["user"]
    mocked_webhook_trigger.assert_called_once_with(
        json.dumps(
            {
                "id": graphene.Node.to_global_id("User", staff_user.id),
                "email": staff_user.email,
                "meta": generate_meta(
                    requestor_data=generate_requestor(
                        SimpleLazyObject(lambda: staff_api_client.user)
                    )
                ),
            },
            cls=CustomJsonEncoder,
        ),
        WebhookEventAsyncType.STAFF_UPDATED,
        [any_webhook],
        staff_user,
        SimpleLazyObject(lambda: staff_api_client.user),
    )


def test_staff_update_email(staff_api_client, permission_manage_staff, media_root):
    query = STAFF_UPDATE_MUTATIONS
    staff_user = User.objects.create(email="staffuser@example.com", is_staff=True)
    assert not staff_user.search_document
    id = graphene.Node.to_global_id("User", staff_user.id)
    new_email = "test@email.com"
    variables = {"id": id, "input": {"email": new_email}}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )

    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    assert data["errors"] == []
    assert data["user"]["userPermissions"] == []
    assert data["user"]["isActive"]
    staff_user.refresh_from_db()
    assert staff_user.search_document == f"{new_email}\n"


@pytest.mark.parametrize("field", ["firstName", "lastName"])
def test_staff_update_name_field(
    field, staff_api_client, permission_manage_staff, media_root
):
    query = STAFF_UPDATE_MUTATIONS
    email = "staffuser@example.com"
    staff_user = User.objects.create(email=email, is_staff=True)
    assert not staff_user.search_document
    id = graphene.Node.to_global_id("User", staff_user.id)
    value = "Name"
    variables = {"id": id, "input": {field: value}}

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )

    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    assert data["errors"] == []
    assert data["user"]["userPermissions"] == []
    assert data["user"]["isActive"]
    staff_user.refresh_from_db()
    assert staff_user.search_document == f"{email}\n{value.lower()}\n"


def test_staff_update_app_no_permission(
    app_api_client, permission_manage_staff, media_root
):
    query = STAFF_UPDATE_MUTATIONS
    staff_user = User.objects.create(email="staffuser@example.com", is_staff=True)
    id = graphene.Node.to_global_id("User", staff_user.id)
    variables = {"id": id, "input": {"isActive": False}}

    response = app_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )

    assert_no_permission(response)


def test_staff_update_groups_and_permissions(
    staff_api_client,
    media_root,
    permission_manage_staff,
    permission_manage_users,
    permission_manage_orders,
    permission_manage_products,
):
    query = STAFF_UPDATE_MUTATIONS
    groups = Group.objects.bulk_create(
        [Group(name="manage users"), Group(name="manage orders"), Group(name="empty")]
    )
    group1, group2, group3 = groups
    group1.permissions.add(permission_manage_users)
    group2.permissions.add(permission_manage_orders)

    staff_user = User.objects.create(email="staffuser@example.com", is_staff=True)
    staff_user.groups.add(group1)

    id = graphene.Node.to_global_id("User", staff_user.id)
    variables = {
        "id": id,
        "input": {
            "addGroups": [
                graphene.Node.to_global_id("Group", gr.pk) for gr in [group2, group3]
            ],
            "removeGroups": [graphene.Node.to_global_id("Group", group1.pk)],
        },
    }

    staff_api_client.user.user_permissions.add(
        permission_manage_users, permission_manage_orders, permission_manage_products
    )

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    assert data["errors"] == []
    assert {perm["code"].lower() for perm in data["user"]["userPermissions"]} == {
        permission_manage_orders.codename,
    }
    assert {group["name"] for group in data["user"]["permissionGroups"]} == {
        group2.name,
        group3.name,
    }


def test_staff_update_out_of_scope_user(
    staff_api_client,
    superuser_api_client,
    permission_manage_staff,
    permission_manage_orders,
    media_root,
):
    """Ensure that staff user cannot update user with wider scope of permission.
    Ensure superuser pass restrictions.
    """
    query = STAFF_UPDATE_MUTATIONS
    staff_user = User.objects.create(email="staffuser@example.com", is_staff=True)
    staff_user.user_permissions.add(permission_manage_orders)
    id = graphene.Node.to_global_id("User", staff_user.id)
    variables = {"id": id, "input": {"isActive": False}}

    # for staff user
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    assert not data["user"]
    assert len(data["errors"]) == 1
    assert data["errors"][0]["field"] == "id"
    assert data["errors"][0]["code"] == AccountErrorCode.OUT_OF_SCOPE_USER.name

    # for superuser
    response = superuser_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    assert data["user"]["email"] == staff_user.email
    assert data["user"]["isActive"] is False
    assert not data["errors"]


def test_staff_update_out_of_scope_groups(
    staff_api_client,
    superuser_api_client,
    permission_manage_staff,
    media_root,
    permission_manage_users,
    permission_manage_orders,
    permission_manage_products,
):
    """Ensure that staff user cannot add to groups which permission scope is wider
    than user's scope.
    Ensure superuser pass restrictions.
    """
    query = STAFF_UPDATE_MUTATIONS

    groups = Group.objects.bulk_create(
        [
            Group(name="manage users"),
            Group(name="manage orders"),
            Group(name="manage products"),
        ]
    )
    group1, group2, group3 = groups

    group1.permissions.add(permission_manage_users)
    group2.permissions.add(permission_manage_orders)
    group3.permissions.add(permission_manage_products)

    staff_user = User.objects.create(email="staffuser@example.com", is_staff=True)
    staff_api_client.user.user_permissions.add(permission_manage_orders)
    id = graphene.Node.to_global_id("User", staff_user.id)
    variables = {
        "id": id,
        "input": {
            "isActive": False,
            "addGroups": [
                graphene.Node.to_global_id("Group", gr.pk) for gr in [group1, group2]
            ],
            "removeGroups": [graphene.Node.to_global_id("Group", group3.pk)],
        },
    }

    # for staff user
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_staff]
    )
    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    errors = data["errors"]
    assert not data["user"]
    assert len(errors) == 2

    expected_errors = [
        {
            "field": "addGroups",
            "code": AccountErrorCode.OUT_OF_SCOPE_GROUP.name,
            "permissions": None,
            "groups": [graphene.Node.to_global_id("Group", group1.pk)],
        },
        {
            "field": "removeGroups",
            "code": AccountErrorCode.OUT_OF_SCOPE_GROUP.name,
            "permissions": None,
            "groups": [graphene.Node.to_global_id("Group", group3.pk)],
        },
    ]
    for error in errors:
        error.pop("message")
        assert error in expected_errors

    # for superuser
    response = superuser_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["staffUpdate"]
    errors = data["errors"]
    assert no