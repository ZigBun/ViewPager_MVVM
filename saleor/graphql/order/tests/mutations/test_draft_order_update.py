import graphene
from prices import TaxedMoney

from .....core.prices import quantize_price
from .....core.taxes import zero_money
from .....order import OrderStatus
from .....order.error_codes import OrderErrorCode
from .....order.models import OrderEvent
from ....tests.utils import get_graphql_content

DRAFT_UPDATE_QUERY = """
        mutation draftUpdate(
        $id: ID!,
        $input: DraftOrderInput!,
        ) {
            draftOrderUpdate(
                id: $id,
                input: $input
            ) {
                errors {
                    field
                    code
                    message
                }
                order {
                    userEmail
                    channel {
                        id
                    }
                }
            }
        }
        """


def test_draft_order_update_existing_channel_id(
    staff_api_client, permission_manage_orders, order_with_lines, channel_PLN
):
    order = order_with_lines
    order.status = OrderStatus.DRAFT
    order.save()
    query = DRAFT_UPDATE_QUERY
    order_id = graphene.Node.to_global_id("Order", order.id)
    channel_id = graphene.Node.to_global_id("Channel", channel_PLN.id)
    variables = {
        "id": order_id,
        "input": {
            "channelId": channel_id,
        },
    }

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    error = content["data"]["draftOrderUpdate"]["errors"][0]

    assert error["code"] == OrderErrorCode.NOT_EDITABLE.name
    assert error["field"] == "channelId"


def test_draft_order_update_voucher_not_available(
    staff_api_client, permission_manage_orders, order_with_lines, voucher
):
    order = order_with_lines
    order.status = OrderStatus.DRAFT
    order.save()
    assert order.voucher is None
    query = DRAFT_UPDATE_QUERY
    order_id = graphene.Node.to_global_id("Order", order.id)
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.id)
    voucher.channel_listings.all().delete()
    variables = {
        "id": order_id,
        "input": {
            "voucher": voucher_id,
        },
    }

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    error = content["data"]["draftOrderUpdate"]["errors"][0]

    assert error["code"] == OrderErrorCode.NOT_AVAILABLE_IN_CHANNEL.name
    assert error["field"] == "voucher"


DRAFT_ORDER_UPDATE_MUTATION = """
    mutation draftUpdate(
        $id: ID!, $voucher: ID!, $customerNote: String, $shippingAddress: AddressInput,
        $externalReference: String
    ) {
        draftOrderUpdate(
            id: $id,
            input: {
                voucher: $voucher,
                customerNote: $customerNote,
                shippingAddress: $shippingAddress,
                externalReference: $externalReference
            }) {
            errors {
                field
                message
                code
            }
            order {
                userEmail
                externalReference
            }
        }
    }
"""


def test_draft_order_update(
    staff_api_client, permission_manage_orders, draft_order, voucher
):
    order = draft_order
    assert not order.voucher
    assert not order.customer_note
    query = DRAFT_ORDER_UPDATE_MUTATION
    order_id = graphene.Node.to_global_id("Order", order.id)
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.id)
    customer_note = "Test customer note"
    external_reference = "test-ext-ref"
    variables = {
        "id": order_id,
        "voucher": voucher_id,
        "customerNote": customer_note,
        "externalReference": external_reference,
    }

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["draftOrderUpdate"]
    assert not data["errors"]
    order.refresh_from_db()
    assert order.voucher
    assert order.customer_note == customer_note
    assert order.search_vector
    assert (
        data["order"]["externalReference"]
        == external_reference
        == order.external_reference
    )


def test_draft_order_update_with_non_draft_order(
    staff_api_client, permission_manage_orders, order_with_lines, voucher
):
    order = order_with_lines
    query = DRAFT_ORDER_UPDATE_MUTATION
    order_id = graphene.Node.to_global_id("Order", order.id)
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.id)
    customer_note = "Test customer note"
    variables = {"id": order_id, "voucher": voucher_id, "customerNote": customer_note}
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    error = content["data"]["draftOrderUpdate"]["errors"][0]
    assert error["field"] == "id"
    assert error["code"] == OrderErrorCode.INVALID.name


def test_draft_order_update_invalid_address(
    staff_api_client,
    permission_manage_orders,
    draft_order,
    voucher,
    graphql_address_data,
):
    order = draft_order
    assert not order.voucher
    assert not order.customer_note
    graphql_address_data["postalCode"] = "TEST TEST invalid postal code 12345"
    query = DRAFT_ORDER_UPDATE_MUTATION
    order_id = graphene.Node.to_global_id("Order", order.id)
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.id)

    variables = {
        "id": order_id,
        "voucher": voucher_id,
        "shippingAddress": graphql_address_data,
    }

    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["draftOrderUpdate"]
    assert len(data["errors"]) == 2
    assert not data["order"]
    assert {error["code"] for error in data["errors"]} == {
        OrderErrorCode.INVALID.name,
        OrderErrorCode.REQUIRED.name,
    }
    assert {error["field"] for error in data["errors"]} == {"postalCode"}


def test_draft_order_update_doing_nothing_generates_no_events(
    staff_api_client, permission_manage_orders, order_with_lines
):
    assert not OrderEvent.objects.exists()

    query = """
        mutation draftUpdate($id: ID!) {
            draftOrderUpdate(id: $id, input: {}) {
                errors {
                    field
                    message
                }
            }
        }
        """
    order_id = graphene.Node.to_global_id("Order", order_with_lines.id)
    response = staff_api_client.post_graphql(
        query, {"id": order_id}, permissions=[permission_manage_orders]
    )
    get_graphql_content(response)

    # Ensure not event was created
    assert not OrderEvent.objects.exists()


def test_draft_order_update_free_shipping_voucher(
    staff_api_client, permission_manage_orders, draft_order, voucher_free_shipping
):
    order = draft_order
    assert not order.voucher
    query = """
        mutation draftUpdate(
            $id: ID!
            $voucher: ID!
        ) {
            draftOrderUpdate(
                id: $id
                input: {
                    voucher: $voucher
                }
            ) {
                errors {
                    field
                    message
                    code
                }
                order {
                    id
                }
            }
        }
        """
    voucher = voucher_free_shipping
    order_id = graphene.Node.to_global_id("Order", order.id)
    voucher_id = graphene.Node.to_global_id("Voucher", voucher.id)
    variables = {
        "id": order_id,
        "voucher": voucher_id,
    }
    response = staff_api_client.post_graphql(
        query, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["dr