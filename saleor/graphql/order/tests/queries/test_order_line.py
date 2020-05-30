from unittest.mock import MagicMock

import graphene
from django.core.files import File
from prices import Money

from .....thumbnail.models import Thumbnail
from .....warehouse.models import Stock
from ....core.enums import ThumbnailFormatEnum
from ....tests.utils import get_graphql_content


def test_order_line_query(staff_api_client, permission_manage_orders, fulfilled_order):
    order = fulfilled_order
    query = """
        query OrdersQuery {
            orders(first: 1) {
                edges {
                    node {
                        lines {
                            thumbnail(size: 540) {
                                url
                            }
                            variant {
                                id
                            }
                            quantity
                            allocations {
                                id
                                quantity
                                warehouse {
                                    id
                                }
                            }
                            unitPrice {
                                currency
                                gross {
                                    amount
                                }
                            }
                            totalPrice {
                                currency
                                gross {
                                    amount
                                }
                            }
                            metadata {
                                key
                                value
                            }
                            privateMetadata {
                                key
                                value
                            }
                            taxClass {
                                name
                            }
                            taxClassName
                            taxClassMetadata {
                                key
                                value
                            }
                            taxClassPrivateMetadata {
                                key
                                value
                            }
                            taxRate
                        }
                    }
                }
            }
        }
    """
    line = order.lines.first()

    metadata_key = "md key"
    metadata_value = "md value"

    line.store_value_in_private_metadata({metadata_key: metadata_value})
    line.store_value_in_metadata({metadata_key: metadata_value})
    line.save()

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    response = staff_api_client.post_graphql(query)
    content = get_graphql_content(response)
    order_data = content["data"]["orders"]["edges"][0]["node"]
    first_order_data_line = order_data["lines"][0]
    variant_id = graphene.Node.to_global_id("ProductVariant", line.variant.pk)

    assert first_order_data_line["thumbnail"] is None
    assert first_order_data_line["variant"]["id"] == variant_id
    assert first_order_data_line["quantity"] == line.quantity
    assert first_order_data_line["unitPrice"]["currency"] == line.unit_price.currency
    assert first_order_data_line["metadata"] == [
        {"key": metadata_key, "value": metadata_value}
    ]
    assert first_order_data_line["privateMetadata"] == [
        {"key": metadata_key, "value": metadata_value}
    ]
    expected_unit_price = Money(
        amount=str(first_order_data_line["unitPrice"]["gross"]["amount"]),
        currency="USD",
    )
    assert first_order_data_line["totalPrice"]["currency"] == line.unit_price.currency
    assert expected_unit_price == line.unit_price.gross

    expected_total_price = Money(
        amount=str(first_order_data_line["totalPrice"]["gross"]["amount"]),
        currency="USD",
    )
    assert expected_total_price == line.unit_price.gross * line.quantity

    allocation = line.allocations.first()
    allocation_id = graphene.Node.to_global_id("Allocation", allocation.pk)
    warehouse_id = graphene.Node.to_global_id(
        "Warehouse", allocation.stock.warehouse.pk
    )
    assert first_order_data_line["allocations"] == [
        {
            "id": allocation_id,
            "quantity": allocation.quantity_allocated,
            "warehouse": {"id": warehouse_id},
        }
    ]

    line_tax_class = line.variant.product.tax_class
    assert first_order_data_line["taxClass"]["name"] == line_tax_class.name
    assert first_order_data_line["taxClassName"] == line_tax_class.name
    assert (
        first_order_data_line["taxClassMetadata"][0]["key"]
        == list(line_tax_class.metadata.keys())[0]
    )
    assert (
        first_order_data_line["taxClassMetadata"][0]["value"]
        == list(line_tax_class.metadata.values())[0]
    )
    assert (
        first_order_data_line["taxClassPrivateMetadata"][0][