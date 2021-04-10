
import graphene
import pytest
from django.db.models import Q
from graphene.utils.str_converters import to_camel_case

from .....attribute import AttributeInputType, AttributeType
from .....attribute.models import Attribute
from .....product import ProductTypeKind
from .....product.models import Category, Collection, Product, ProductType
from .....tests.utils import dummy_editorjs
from ....tests.utils import (
    assert_no_permission,
    get_graphql_content,
    get_graphql_content_from_response,
)


def test_get_single_attribute_by_id_as_customer(
    user_api_client, color_attribute_without_values
):
    attribute_gql_id = graphene.Node.to_global_id(
        "Attribute", color_attribute_without_values.id
    )
    query = """