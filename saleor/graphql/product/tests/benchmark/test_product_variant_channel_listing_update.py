import graphene
import pytest

from .....product.models import ProductChannelListing, ProductMedia, VariantMedia
from ....tests.utils import get_graphql_content


@pytest.mark.django_db
@pytest.mark.count_queries(autouse=False)
def test_variant_channel_listing_update(
    staff_api_client,
    settings,
    product_with_variant_with_two_attributes,
    permission_manage_products,
    channel_USD,
    channe