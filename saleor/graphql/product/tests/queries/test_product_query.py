from datetime import timedelta
from unittest.mock import MagicMock

import graphene
import pytest
from django.contrib.sites.models import Site
from django.core.files import File
from django.utils import timezone
from measurement.measures import Weight

from .....attribute.models import AttributeValue
from .....attribute.utils import associate_attribute_values_to_instance
from .....core.units import WeightUnits
from .....product.models import (
    Product,
    ProductChannelListing,
    ProductVariantChannelListing,
)
from .....tests.utils import dummy_editorjs
from .....thumbnail.models import Thumbnail
from .....warehouse.models import Allocation, Stock
from ....core.enums import ThumbnailFormatEnum
from ....tests.utils import get_graphql_content, get_graphql_content_from_response

QUERY_PRODUCT = """
    query ($id: ID, $slug: String, $channel:String){
        product(
            id: $id,
            slug: $slug,
            channel: $channel
        ) {
            id
            name
            weight {
                unit
                value
            }
            availableForPurchase
            availableForPurchaseAt
            isAvailableForPurchase
            isAvailable
        }
    }
"""


def test_product_query_by_id_available_as_staff_user(
    staff_api_client, permission_manage_products, product, channel_USD
):
    variables = {
        "id": graphene.Node.to_global_id("Product", product.pk),
        "channel": channel_USD.slug,
    }

    response = staff_api_client.post_graphql(
        QUERY_PRODUCT,
        variables=variables,
        permissions=(permission_manage_products,),
        check_no_permissions=False,
    )
    content = get_graphql_content(response)
    product_data = content["data"]["product"]
    assert product_data is not None
    assert product_data["name"] == product.name


def test_product_query_description(
    staff_api_client, permission_manage_products, product, channel_USD
):
    query = """
        query ($id: ID, $slug: String, $channel:String){
            product(
                id: $id,
                slug: $slug,
                channel: $channel
            ) {
                id
                name
                description
                descriptionJson
            }
        }
        """
    description = dummy_editorjs("Test description.", json_format=True)
    product.description = dummy_editorjs("Test description.")
    product.save()
    variables = {
        "id": graphene.Node.to_global_id("Product", product.p