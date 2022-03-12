import datetime

import graphene
import pytz

from .....product.error_codes import CollectionErrorCode
from ....tests.utils import get_graphql_content

COLLECTION_CHANNEL_LISTING_UPDATE_MUTATION = """
mutation UpdateCollectionChannelListing(
    $id: ID!
    $input: CollectionChannelListingUpdateInput!
) {
    collectionChannelListingUpdate(id: $id, input: $input) {
        errors {
            field
            message
            code
            channels
        }
        collection {
     