from unittest.mock import patch

import graphene

from ....account.error_codes import AccountErrorCode
from ....account.models import Group, User
from ....permission.enums import AccountPermissions, OrderPermissions
from ...tests.utils import assert_no_permission, get_graphql_content

CUSTOMER_BULK_DELETE_MUTATION = """
    mutation customerBulkDelete($ids: [ID!]!) {
        customerBulkDelete(ids: $ids) {
            count
        }
    }
"""


@patch("saleor.graphql.account.utils.account_events.customer_deleted_event")
def test_delete_customers(
    mocked_deletion_event,
    staff_api_client,
    staff_user,
    user_list,
    permission_manage_users,
):
    user_1, user_2, *users = user_list

    query = CUSTOMER_BULK_DELETE_MUTATION

    variables = {
        "ids": [graphene.Node.to_global_id("User", user.id) for user in user_list]
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_users]
    )
    content = get_graphql_content(response)

    assert content["data"]["customerBulkDelete"]["count"] == 2

    deleted_customers = [user_1, user_2]
    saved_customers = users

    # Ensure given customers were properly deleted and others properly saved
    # and any related event was properly triggered

    # Ensure the customers were properly deleted and others were preserved
    assert not User.objects.