
import json
from unittest.mock import patch

import graphene
import pytest
from django.utils.functional import SimpleLazyObject
from freezegun import freeze_time

from ....account.error_codes import PermissionGroupErrorCode
from ....account.models import Group, User
from ....core.utils.json_serializer import CustomJsonEncoder
from ....permission.enums import AccountPermissions, AppPermission, OrderPermissions
from ....webhook.event_types import WebhookEventAsyncType
from ....webhook.payloads import generate_meta, generate_requestor
from ...tests.utils import (
    assert_no_permission,
    get_graphql_content,
    get_graphql_content_from_response,
)

PERMISSION_GROUP_CREATE_MUTATION = """
    mutation PermissionGroupCreate(
        $input: PermissionGroupCreateInput!) {
        permissionGroupCreate(
            input: $input)
        {
            group{
                id
                name
                permissions {
                    name
                    code
                }
                users {
                    email
                }
            }
            errors{
                field
                code
                permissions
                users
                message
            }
        }
    }
    """


def test_permission_group_create_mutation(
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {
        "input": {
            "name": "New permission group",
            "addPermissions": [
                AccountPermissions.MANAGE_USERS.name,
                AppPermission.MANAGE_APPS.name,
            ],
            "addUsers": [
                graphene.Node.to_global_id("User", user.id) for user in staff_users
            ],
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    permission_group_data = data["group"]

    group = Group.objects.get()
    assert permission_group_data["name"] == group.name == variables["input"]["name"]
    permissions = {
        permission["name"] for permission in permission_group_data["permissions"]
    }
    assert set(group.permissions.all().values_list("name", flat=True)) == permissions
    permissions_codes = {
        permission["code"].lower()
        for permission in permission_group_data["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("codename", flat=True))
        == permissions_codes
        == set(perm.lower() for perm in variables["input"]["addPermissions"])
    )
    assert (
        {user["email"] for user in permission_group_data["users"]}
        == {user.email for user in staff_users}
        == set(group.user_set.all().values_list("email", flat=True))
    )
    assert data["errors"] == []


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_permission_group_create_mutation_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {
        "input": {
            "name": "New permission group",
            "addPermissions": [
                AccountPermissions.MANAGE_USERS.name,
                AppPermission.MANAGE_APPS.name,
            ],
            "addUsers": [
                graphene.Node.to_global_id("User", user.id) for user in staff_users
            ],
        }
    }

    # when
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    group = Group.objects.last()

    # then
    assert not data["errors"]
    mocked_webhook_trigger.assert_called_once_with(
        json.dumps(
            {
                "id": graphene.Node.to_global_id("Group", group.id),
                "meta": generate_meta(
                    requestor_data=generate_requestor(
                        SimpleLazyObject(lambda: staff_api_client.user)
                    )
                ),
            },
            cls=CustomJsonEncoder,
        ),
        WebhookEventAsyncType.PERMISSION_GROUP_CREATED,
        [any_webhook],
        group,
        SimpleLazyObject(lambda: staff_api_client.user),
    )


def test_permission_group_create_app_no_permission(
    staff_users,
    permission_manage_staff,
    app_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {
        "input": {
            "name": "New permission group",
            "addPermissions": [
                AccountPermissions.MANAGE_USERS.name,
                AppPermission.MANAGE_APPS.name,
            ],
            "addUsers": [
                graphene.Node.to_global_id("User", user.id) for user in staff_users
            ],
        }
    }
    response = app_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )

    assert_no_permission(response)


def test_permission_group_create_mutation_only_required_fields(
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {"input": {"name": "New permission group"}}
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    permission_group_data = data["group"]

    group = Group.objects.get()
    assert permission_group_data["name"] == group.name == variables["input"]["name"]
    assert permission_group_data["permissions"] == []
    assert not group.permissions.all()
    assert permission_group_data["users"] == []
    assert not group.user_set.all()


def test_permission_group_create_mutation_only_required_fields_not_none(
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {
        "input": {
            "name": "New permission group",
            "addUsers": None,
            "addPermissions": None,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    permission_group_data = data["group"]

    group = Group.objects.get()
    assert permission_group_data["name"] == group.name == variables["input"]["name"]
    assert permission_group_data["permissions"] == []
    assert not group.permissions.all()
    assert permission_group_data["users"] == []
    assert not group.user_set.all()


def test_permission_group_create_mutation_lack_of_permission(
    staff_user,
    permission_manage_staff,
    staff_api_client,
    superuser_api_client,
    permission_manage_orders,
):
    """Ensue staff user can't create group with wider scope of permissions.
    Ensure that superuser pass restrictions.
    """
    staff_user.user_permissions.add(permission_manage_orders)
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {
        "input": {
            "name": "New permission group",
            "addPermissions": [
                AccountPermissions.MANAGE_USERS.name,
                OrderPermissions.MANAGE_ORDERS.name,
                AppPermission.MANAGE_APPS.name,
            ],
        }
    }

    # for staff user
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    errors = data["errors"]

    assert len(errors) == 1
    assert errors[0]["field"] == "addPermissions"
    assert errors[0]["code"] == PermissionGroupErrorCode.OUT_OF_SCOPE_PERMISSION.name
    assert set(errors[0]["permissions"]) == {
        AccountPermissions.MANAGE_USERS.name,
        AppPermission.MANAGE_APPS.name,
    }
    assert errors[0]["users"] is None

    # for superuser
    response = superuser_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    errors = data["errors"]

    assert not errors
    group = Group.objects.get()
    assert data["group"]["name"] == group.name == variables["input"]["name"]
    permissions_codes = {
        permission["code"].lower() for permission in data["group"]["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("codename", flat=True))
        == permissions_codes
        == set(perm.lower() for perm in variables["input"]["addPermissions"])
    )


def test_permission_group_create_mutation_group_exists(
    staff_user,
    permission_manage_staff,
    staff_api_client,
    permission_group_manage_users,
    permission_manage_users,
    permission_manage_apps,
):
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {
        "input": {
            "name": permission_group_manage_users.name,
            "addPermissions": [
                AccountPermissions.MANAGE_USERS.name,
                AppPermission.MANAGE_APPS.name,
            ],
            "addUsers": [graphene.Node.to_global_id("User", staff_user.id)],
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    errors = data["errors"]
    permission_group_data = data["group"]

    assert permission_group_data is None
    assert len(errors) == 1
    assert errors[0]["field"] == "name"
    assert errors[0]["code"] == PermissionGroupErrorCode.UNIQUE.name
    assert errors[0]["permissions"] is None
    assert errors[0]["users"] is None


def test_permission_group_create_mutation_add_customer_user(
    staff_user,
    customer_user,
    permission_manage_staff,
    staff_api_client,
    superuser_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    """Ensure creating permission group with customer user in input field for adding
    users failed. Mutations should failed. Error should contains list of wrong users
    IDs.
    Ensure this mutation also fail for superuser.
    """

    second_customer = User.objects.create(
        email="second_customer@test.com", password="test"
    )

    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    query = PERMISSION_GROUP_CREATE_MUTATION

    user_ids = [
        graphene.Node.to_global_id("User", user.id)
        for user in [staff_user, customer_user, second_customer]
    ]
    variables = {
        "input": {
            "name": "New permission group",
            "addPermissions": [
                AccountPermissions.MANAGE_USERS.name,
                AppPermission.MANAGE_APPS.name,
            ],
            "addUsers": user_ids,
        }
    }

    # for staff user
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    errors = data["errors"]

    assert errors
    assert len(errors) == 1
    assert errors[0]["field"] == "addUsers"
    assert errors[0]["permissions"] is None
    assert set(errors[0]["users"]) == set(user_ids[1:])
    assert errors[0]["code"] == PermissionGroupErrorCode.ASSIGN_NON_STAFF_MEMBER.name
    assert data["group"] is None

    # for superuser
    response = superuser_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    errors = data["errors"]

    assert errors
    assert len(errors) == 1
    assert errors[0]["field"] == "addUsers"
    assert errors[0]["permissions"] is None
    assert set(errors[0]["users"]) == set(user_ids[1:])
    assert errors[0]["code"] == PermissionGroupErrorCode.ASSIGN_NON_STAFF_MEMBER.name
    assert data["group"] is None


def test_permission_group_create_mutation_lack_of_permission_and_customer_user(
    staff_user,
    customer_user,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
):
    staff_user.user_permissions.add(permission_manage_users)
    query = PERMISSION_GROUP_CREATE_MUTATION

    user_ids = [
        graphene.Node.to_global_id("User", user.id)
        for user in [staff_user, customer_user]
    ]
    variables = {
        "input": {
            "name": "New permission group",
            "addPermissions": [
                AccountPermissions.MANAGE_USERS.name,
                AppPermission.MANAGE_APPS.name,
            ],
            "addUsers": user_ids,
        }
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    errors = data["errors"]

    assert errors
    assert len(errors) == 2
    assert {error["field"] for error in errors} == {"addUsers", "addPermissions"}
    assert [AppPermission.MANAGE_APPS.name] in [
        error["permissions"] for error in errors
    ]
    assert user_ids[1:] in [error["users"] for error in errors]
    assert {error["code"] for error in errors} == {
        PermissionGroupErrorCode.ASSIGN_NON_STAFF_MEMBER.name,
        PermissionGroupErrorCode.OUT_OF_SCOPE_PERMISSION.name,
    }
    assert data["group"] is None


def test_permission_group_create_mutation_requestor_does_not_have_all_users_perms(
    staff_users,
    permission_group_manage_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    """Ensure user can create group with user whose permission scope
    is wider than requestor scope.
    """

    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_apps)
    permission_group_manage_users.user_set.add(staff_users[1])
    query = PERMISSION_GROUP_CREATE_MUTATION

    variables = {
        "input": {
            "name": "New permission group",
            "addPermissions": [AppPermission.MANAGE_APPS.name],
            "addUsers": [
                graphene.Node.to_global_id("User", user.id) for user in staff_users
            ],
        }
    }

    # for staff user
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupCreate"]
    errors = data["errors"]

    assert not errors
    group_name = variables["input"]["name"]
    group = Group.objects.get(name=group_name)
    assert data["group"]["name"] == group.name == group_name
    permissions_codes = {
        permission["code"].lower() for permission in data["group"]["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("codename", flat=True))
        == permissions_codes
        == set(perm.lower() for perm in variables["input"]["addPermissions"])
    )
    assert (
        {user["email"] for user in data["group"]["users"]}
        == {user.email for user in staff_users}
        == set(group.user_set.all().values_list("email", flat=True))
    )


PERMISSION_GROUP_UPDATE_MUTATION = """
    mutation PermissionGroupUpdate(
        $id: ID!, $input: PermissionGroupUpdateInput!) {
        permissionGroupUpdate(
            id: $id, input: $input)
        {
            group{
                id
                name
                permissions {
                    name
                    code
                }
                users {
                    email
                }
            }
            errors{
                field
                code
                permissions
                users
                message
            }
        }
    }
    """


def test_permission_group_update_mutation(
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_apps,
    permission_manage_users,
):
    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_apps, permission_manage_users)
    query = PERMISSION_GROUP_UPDATE_MUTATION

    group1, group2 = Group.objects.bulk_create(
        [Group(name="manage users"), Group(name="manage staff and users")]
    )
    group1.permissions.add(permission_manage_users)
    group2.permissions.add(permission_manage_users, permission_manage_staff)

    group1_user = staff_users[1]
    group1.user_set.add(group1_user)
    group2.user_set.add(staff_user)

    # set of users emails being in a group
    users = set(group1.user_set.values_list("email", flat=True))

    variables = {
        "id": graphene.Node.to_global_id("Group", group1.id),
        "input": {
            "name": "New permission group",
            "addPermissions": [AppPermission.MANAGE_APPS.name],
            "removePermissions": [AccountPermissions.MANAGE_USERS.name],
            "addUsers": [graphene.Node.to_global_id("User", staff_user.pk)],
            "removeUsers": [graphene.Node.to_global_id("User", group1_user.pk)],
        },
    }
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]

    # remove and add user email for comparing users set
    users.remove(group1_user.email)
    users.add(staff_user.email)

    group1.refresh_from_db()
    assert permission_group_data["name"] == group1.name
    permissions = {
        permission["name"] for permission in permission_group_data["permissions"]
    }
    assert set(group1.permissions.all().values_list("name", flat=True)) == permissions
    permissions_codes = {
        permission["code"].lower()
        for permission in permission_group_data["permissions"]
    }
    assert (
        set(group1.permissions.all().values_list("codename", flat=True))
        == permissions_codes
    )
    assert set(group1.user_set.all().values_list("email", flat=True)) == users
    assert data["errors"] == []


@freeze_time("2018-05-31 12:00:01")
@patch("saleor.plugins.webhook.plugin.get_webhooks_for_event")
@patch("saleor.plugins.webhook.plugin.trigger_webhooks_async")
def test_permission_group_update_mutation_trigger_webhook(
    mocked_webhook_trigger,
    mocked_get_webhooks_for_event,
    any_webhook,
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_apps,
    permission_manage_users,
    settings,
):
    # given
    mocked_get_webhooks_for_event.return_value = [any_webhook]
    settings.PLUGINS = ["saleor.plugins.webhook.plugin.WebhookPlugin"]

    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_apps, permission_manage_users)
    query = PERMISSION_GROUP_UPDATE_MUTATION

    group1, group2 = Group.objects.bulk_create(
        [Group(name="manage users"), Group(name="manage staff and users")]
    )
    group1.permissions.add(permission_manage_users)
    group2.permissions.add(permission_manage_users, permission_manage_staff)

    group1_user = staff_users[1]
    group1.user_set.add(group1_user)
    group2.user_set.add(staff_user)

    variables = {
        "id": graphene.Node.to_global_id("Group", group1.id),
        "input": {
            "name": "New permission group",
            "addPermissions": [AppPermission.MANAGE_APPS.name],
            "removePermissions": [AccountPermissions.MANAGE_USERS.name],
            "addUsers": [graphene.Node.to_global_id("User", staff_user.pk)],
            "removeUsers": [graphene.Node.to_global_id("User", group1_user.pk)],
        },
    }

    # when
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    group1.refresh_from_db()

    # then
    assert not data["errors"]
    mocked_webhook_trigger.assert_called_once_with(
        json.dumps(
            {
                "id": graphene.Node.to_global_id("Group", group1.id),
                "meta": generate_meta(
                    requestor_data=generate_requestor(
                        SimpleLazyObject(lambda: staff_api_client.user)
                    )
                ),
            },
            cls=CustomJsonEncoder,
        ),
        WebhookEventAsyncType.PERMISSION_GROUP_UPDATED,
        [any_webhook],
        group1,
        SimpleLazyObject(lambda: staff_api_client.user),
    )


def test_permission_group_update_mutation_removing_perm_left_not_manageable_perms(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    staff_api_client,
    permission_manage_apps,
    permission_manage_users,
):
    """Ensure user cannot remove permissions if it left not meanagable perms."""
    staff_user.user_permissions.add(permission_manage_apps, permission_manage_users)
    group = permission_group_manage_users
    query = PERMISSION_GROUP_UPDATE_MUTATION

    group_user = group.user_set.first()
    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {
            "name": "New permission group",
            "addPermissions": [AppPermission.MANAGE_APPS.name],
            "removePermissions": [AccountPermissions.MANAGE_USERS.name],
            "addUsers": [graphene.Node.to_global_id("User", staff_user.pk)],
            "removeUsers": [graphene.Node.to_global_id("User", group_user.pk)],
        },
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    errors = data["errors"]

    assert not data["group"]
    assert len(errors) == 1
    assert errors[0]["field"] == "removePermissions"
    assert (
        errors[0]["code"]
        == PermissionGroupErrorCode.LEFT_NOT_MANAGEABLE_PERMISSION.name
    )
    assert errors[0]["permissions"] == [AccountPermissions.MANAGE_USERS.name]
    assert errors[0]["users"] is None
    assert staff_user.groups.count() == 0


def test_permission_group_update_mutation_superuser_can_remove_any_perms(
    permission_group_manage_users,
    permission_manage_staff,
    superuser_api_client,
    staff_user,
    permission_manage_apps,
    permission_manage_users,
):
    """Ensure superuser can remove any permissions."""
    group = permission_group_manage_users
    query = PERMISSION_GROUP_UPDATE_MUTATION

    # set of users emails being in a group
    users = set(group.user_set.values_list("email", flat=True))

    group_user = group.user_set.first()
    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {
            "name": "New permission group",
            "addPermissions": [AppPermission.MANAGE_APPS.name],
            "removePermissions": [AccountPermissions.MANAGE_USERS.name],
            "addUsers": [graphene.Node.to_global_id("User", staff_user.pk)],
            "removeUsers": [graphene.Node.to_global_id("User", group_user.pk)],
        },
    }
    response = superuser_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]

    # remove and add user email for comparing users set
    users.remove(group_user.email)
    users.add(staff_user.email)

    group.refresh_from_db()
    assert permission_group_data["name"] == group.name
    permissions = {
        permission["name"] for permission in permission_group_data["permissions"]
    }
    assert set(group.permissions.all().values_list("name", flat=True)) == permissions
    permissions_codes = {
        permission["code"].lower()
        for permission in permission_group_data["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("codename", flat=True))
        == permissions_codes
    )
    assert set(group.user_set.all().values_list("email", flat=True)) == users
    assert data["errors"] == []


def test_permission_group_update_mutation_app_no_permission(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    app_api_client,
    permission_manage_apps,
    permission_manage_users,
):
    staff_user.user_permissions.add(permission_manage_apps, permission_manage_users)
    group = permission_group_manage_users
    query = PERMISSION_GROUP_UPDATE_MUTATION

    group_user = group.user_set.first()
    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {
            "name": "New permission group",
            "addPermissions": [AppPermission.MANAGE_APPS.name],
            "removePermissions": [AccountPermissions.MANAGE_USERS.name],
            "addUsers": [graphene.Node.to_global_id("User", staff_user.pk)],
            "removeUsers": [graphene.Node.to_global_id("User", group_user.pk)],
        },
    }
    response = app_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )

    assert_no_permission(response)


def test_permission_group_update_mutation_remove_me_from_last_group(
    permission_group_manage_users,
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
):
    """Ensure mutation failed when user removing himself from user's last group."""
    staff_user, staff_user1, staff_user2 = staff_users
    staff_user.user_permissions.add(permission_manage_users)
    group = permission_group_manage_users
    group.permissions.add(permission_manage_staff)
    # ensure user is in group
    group.user_set.add(staff_user, staff_user1)
    assert staff_user.groups.count() == 1

    query = PERMISSION_GROUP_UPDATE_MUTATION

    staff_user_id = graphene.Node.to_global_id("User", staff_user.pk)
    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {"removeUsers": [staff_user_id]},
    }
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]
    errors = data["errors"]

    assert not permission_group_data
    assert len(errors) == 1
    assert errors[0]["field"] == "removeUsers"
    assert (
        errors[0]["code"] == PermissionGroupErrorCode.CANNOT_REMOVE_FROM_LAST_GROUP.name
    )
    assert errors[0]["permissions"] is None
    assert errors[0]["users"] == [staff_user_id]
    assert staff_user.groups.count() == 1


def test_permission_group_update_mutation_remove_me_from_not_last_group(
    permission_group_manage_users,
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_orders,
):
    """Ensure user can remove himself from group if he is a member of another group."""
    staff_user, staff_user1, _ = staff_users
    staff_user.user_permissions.add(permission_manage_users)
    groups = Group.objects.bulk_create(
        [Group(name="manage users"), Group(name="manage staff and users")]
    )
    group1, group2 = groups

    group1.permissions.add(permission_manage_users)
    group2.permissions.add(permission_manage_users, permission_manage_staff)

    # ensure user is in group
    group1.user_set.add(staff_user)
    group2.user_set.add(staff_user, staff_user1)

    assert staff_user.groups.count() == 2

    query = PERMISSION_GROUP_UPDATE_MUTATION

    staff_user_id = graphene.Node.to_global_id("User", staff_user.pk)
    variables = {
        "id": graphene.Node.to_global_id("Group", group1.id),
        "input": {"removeUsers": [staff_user_id]},
    }
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]
    errors = data["errors"]

    assert not errors
    assert staff_user_id not in permission_group_data["users"]
    assert staff_user.groups.count() == 1


def test_permission_group_update_mutation_remove_last_user_from_group(
    permission_group_manage_users,
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
):
    """Ensure user can remove last user from the group."""
    staff_user, staff_user1, staff_user2 = staff_users
    staff_user.user_permissions.add(permission_manage_users)
    groups = Group.objects.bulk_create(
        [Group(name="manage users"), Group(name="manage staff and users")]
    )
    group1, group2 = groups
    group1.permissions.add(permission_manage_users)
    group2.permissions.add(permission_manage_users, permission_manage_staff)

    group1.user_set.add(staff_user1)
    group2.user_set.add(staff_user2)

    # ensure group contains only 1 user
    assert group1.user_set.count() == 1

    group_user = group1.user_set.first()

    query = PERMISSION_GROUP_UPDATE_MUTATION

    group_user_id = graphene.Node.to_global_id("User", group_user.pk)
    variables = {
        "id": graphene.Node.to_global_id("Group", group1.id),
        "input": {"removeUsers": [group_user_id]},
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]
    errors = data["errors"]

    assert not errors
    assert staff_user.groups.count() == 0
    assert permission_group_data["users"] == []


def test_permission_group_update_mutation_only_name(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
):
    """Ensure mutation update group when only name are passed in input."""
    staff_user.user_permissions.add(permission_manage_staff, permission_manage_users)
    group = permission_group_manage_users
    old_group_name = group.name
    query = PERMISSION_GROUP_UPDATE_MUTATION

    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {"name": "New permission group"},
    }
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]

    group = Group.objects.get()
    assert group.name != old_group_name
    assert permission_group_data["name"] == group.name
    assert group.permissions.all().count() == 1
    assert group.permissions.first() == permission_manage_users
    result_permissions = {
        permission["name"] for permission in permission_group_data["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("name", flat=True))
        == result_permissions
    )
    permissions_codes = {
        permission["code"].lower()
        for permission in permission_group_data["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("codename", flat=True))
        == permissions_codes
    )
    assert data["errors"] == []


def test_permission_group_update_mutation_only_name_other_fields_with_none(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
):
    """Ensure mutation update group when only name are passed in input."""
    staff_user.user_permissions.add(permission_manage_staff, permission_manage_users)
    group = permission_group_manage_users
    old_group_name = group.name
    query = PERMISSION_GROUP_UPDATE_MUTATION

    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {
            "name": "New permission group",
            "addPermissions": None,
            "removePermissions": None,
            "addUsers": None,
            "removeUsers": None,
        },
    }
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]

    group = Group.objects.get()
    assert group.name != old_group_name
    assert permission_group_data["name"] == group.name
    assert group.permissions.all().count() == 1
    assert group.permissions.first() == permission_manage_users
    result_permissions = {
        permission["name"] for permission in permission_group_data["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("name", flat=True))
        == result_permissions
    )
    permissions_codes = {
        permission["code"].lower()
        for permission in permission_group_data["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("codename", flat=True))
        == permissions_codes
    )
    assert data["errors"] == []


def test_permission_group_update_mutation_with_name_which_exists(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
):
    """Ensure mutation failed where updating name with value which already is a name of
    different group.
    """
    staff_user.user_permissions.add(permission_manage_staff, permission_manage_users)
    group = permission_group_manage_users
    old_group_name = group.name
    query = PERMISSION_GROUP_UPDATE_MUTATION

    new_name = "New permission group"
    Group.objects.create(name=new_name)

    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {"name": new_name},
    }
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]
    errors = data["errors"]

    group.refresh_from_db()
    assert not permission_group_data
    assert len(errors) == 1
    assert errors[0]["field"] == "name"
    assert errors[0]["code"] == PermissionGroupErrorCode.UNIQUE.name
    assert errors[0]["permissions"] is None
    assert errors[0]["users"] is None
    assert group.name == old_group_name


def test_permission_group_update_mutation_only_permissions(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    """Ensure mutation update group when only permissions are passed in input."""
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    group = permission_group_manage_users
    old_group_name = group.name
    query = PERMISSION_GROUP_UPDATE_MUTATION

    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {"addPermissions": [AppPermission.MANAGE_APPS.name]},
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    permission_group_data = data["group"]

    group = Group.objects.get()
    assert group.name == old_group_name
    assert permission_group_data["name"] == group.name
    permissions = {
        permission["name"] for permission in permission_group_data["permissions"]
    }
    assert set(group.permissions.all().values_list("name", flat=True)) == permissions
    assert data["errors"] == []


def test_permission_group_update_mutation_no_input_data(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    permission_manage_users,
    staff_api_client,
):
    """Ensure mutation doesn't change group when input is empty."""
    staff_user.user_permissions.add(permission_manage_staff, permission_manage_users)
    group = permission_group_manage_users
    query = PERMISSION_GROUP_UPDATE_MUTATION

    variables = {"id": graphene.Node.to_global_id("Group", group.id), "input": {}}
    response = staff_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    errors = data["errors"]
    permission_group_data = data["group"]

    assert errors == []
    assert permission_group_data["name"] == group.name
    permissions = {
        permission["name"] for permission in permission_group_data["permissions"]
    }
    assert set(group.permissions.all().values_list("name", flat=True)) == permissions


def test_permission_group_update_mutation_user_cannot_manage_group(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    staff_api_client,
    superuser_api_client,
    permission_manage_apps,
):
    """Ensure that update mutation failed when user try to update group for which
    he doesn't have permission.
    Ensure superuser pass restrictions.
    """
    staff_user.user_permissions.add(permission_manage_apps)
    group = permission_group_manage_users
    query = PERMISSION_GROUP_UPDATE_MUTATION

    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {
            "name": "New permission group",
            "addPermissions": [AppPermission.MANAGE_APPS.name],
        },
    }

    # for staff user
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    errors = data["errors"]

    assert len(errors) == 1
    assert errors[0]["code"] == PermissionGroupErrorCode.OUT_OF_SCOPE_PERMISSION.name
    assert errors[0]["field"] is None

    # for superuser
    response = superuser_api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    errors = data["errors"]

    group_name = variables["input"]["name"]
    group = Group.objects.get(name=group_name)
    assert not errors
    assert data["group"]["name"] == group_name == group.name
    permissions_codes = {
        permission["code"].lower() for permission in data["group"]["permissions"]
    }
    assert (
        set(group.permissions.all().values_list("codename", flat=True))
        == permissions_codes
    )
    assert variables["input"]["addPermissions"][0].lower() in permissions_codes


def test_permission_group_update_mutation_user_in_list_to_add_and_remove(
    permission_group_manage_users,
    staff_users,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
):
    """Ensure update mutation failed when user IDs are in both lists for adding
    and removing. Ensure mutation contains list of user IDs which cause
    the problem.
    """
    staff_user = staff_users[0]
    staff_user.user_permissions.add(permission_manage_users, permission_manage_apps)
    group = permission_group_manage_users
    query = PERMISSION_GROUP_UPDATE_MUTATION

    staff_user2_id = graphene.Node.to_global_id("User", staff_users[1].pk)

    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {
            "name": "New permission group",
            "addUsers": [
                graphene.Node.to_global_id("User", user.pk) for user in staff_users
            ],
            "removeUsers": [staff_user2_id],
        },
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    errors = data["errors"]

    assert len(errors) == 1
    assert errors[0]["code"] == PermissionGroupErrorCode.DUPLICATED_INPUT_ITEM.name
    assert errors[0]["field"] == "users"
    assert errors[0]["permissions"] is None
    assert errors[0]["users"] == [staff_user2_id]


def test_permission_group_update_mutation_permissions_in_list_to_add_and_remove(
    permission_group_manage_users,
    staff_user,
    permission_manage_staff,
    staff_api_client,
    permission_manage_users,
    permission_manage_apps,
    permission_manage_orders,
):
    """Ensure update mutation failed when permission items are in both lists for
    adding and removing. Ensure mutation contains list of permissions which cause
    the problem.
    """
    staff_user.user_permissions.add(
        permission_manage_users,
        permission_manage_apps,
        permission_manage_orders,
    )
    group = permission_group_manage_users
    query = PERMISSION_GROUP_UPDATE_MUTATION

    permissions = [
        OrderPermissions.MANAGE_ORDERS.name,
        AppPermission.MANAGE_APPS.name,
    ]
    variables = {
        "id": graphene.Node.to_global_id("Group", group.id),
        "input": {
            "name": "New permission group",
            "addPermissions": permissions,
            "removePermissions": permissions,
        },
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=(permission_manage_staff,)
    )
    content = get_graphql_content(response)
    data = content["data"]["permissionGroupUpdate"]
    errors = data["errors"]

    assert len(errors) == 1