from saleor.graphql.core.utils import to_global_id_or_none
from saleor.graphql.tests.utils import get_graphql_content

CHECKOUT_QUERY = """
query getCheckout($token: UUID) {
    checkout(token: $token) 