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
     