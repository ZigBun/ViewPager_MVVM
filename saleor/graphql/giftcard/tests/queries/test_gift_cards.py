import graphene

from ....tests.utils import get_graphql_content

QUERY_GIFT_CARDS = """
    query giftCards{
        giftCards(first: 10) {
            edges {
                node {
                    id
                    last4CodeChars
                }
            }
            totalCount
        }
    }
"""


def test_query_gift_cards_by_staff(
    staff_api_client, gift_card, gift_card_created_by_staff, permission_manage_gift_card
):
    # given
    query = QUERY_GIFT_CARDS
    gift_card_id = graphene.Node.to_global_id("GiftCard", gift_card.pk)
    gift_card_created_by_staff_id = graphene.Node.to_global_id(
 