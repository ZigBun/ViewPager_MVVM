from unittest.mock import patch

import graphene
import pytest

from .....discount.utils import fetch_catalogue_info
from ....tests.utils import get_graphql_content
from ...mutations.utils import convert_catalogue_info_to_global_ids

SALE_DELETE_MUTATION = """
    mutation DeleteSale($id: ID!) {
        saleDelete(id: $id) {
            sale {
                name
                id
            }
            errors {
                field
                code
                message
            }
            }
        }
"""


@patch("saleor.plugins.manager.PluginsManager.sale_deleted")
def test_sale_delete_mutation(
    delete