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

    account_deactivated_event = account_events.CustomerEvent.