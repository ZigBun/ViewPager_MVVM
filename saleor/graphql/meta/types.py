from typing import Optional

import graphene
from graphene.types.generic import GenericScalar

from ...checkout.models import Checkout
from ...checkout.utils import get_or_create_checkout_metadata
from ...core.models import ModelWithMetadata
from ..channel import ChannelContext
from ..core import ResolveInfo
from ..core.types import NonNullList
from .resolvers import (
    check_private_metadata_privilege,
    resolve_metadata,
    resolve_object_with_metadata_type,
    resolve_private_metadata,
)


class MetadataItem(graphene.ObjectType):
    key = graphene.String(required=True, description="Key of a metadata item.")
    value = graphene.String(required=True, description="Value of a metadata item.")


class Metadata(GenericScalar):
    """Metadata is a map of key-value pairs, both keys and values are `String`.

    Example:
    ```
    {
        "key1": "value1",
        "key2": "value2"
    }
    ```

    """


def _filter_metadata(metadata, keys):
    if keys is None:
        return metadata
    return {key: value for key, value in metadata.items() if key in keys}


class MetadataDescription:
    PRIVATE_METADATA = (
        "List of private metadata items. Requires staff permissions to access."
    )
    PRIVATE_METAFIELD = (
        "A single key from private metadata. "
        "Requires staff permissions to access.\n\n"
        "Tip: Use GraphQL aliases to fetch multiple keys."
    )
    PRIVATE_METAFIELDS = (
        "Private metadata. Requires staff permissions to access. "
        "Use `keys` to control which fields you want to include. "
        "The default is to include everything."
    )
    METADATA = "List of public metadata items. Can be accessed without permissions."
    METAFIELD = (
        "A single key from public metadata.\n\n"
        "Tip: Use GraphQL aliases to fetch multiple keys."
    )
    METAFIELDS = (
        "Public metadata. Use `keys` to control which fields you want to include. "
        "The default is to include everything."
    )


class ObjectWithMetadata(graphene.Interface):
    private_metadata = NonNullList(
        MetadataItem,
        required=True,
        description=(
            "List of private metadata items. Requires staff permissions to access."
        ),
    )
    private_metafield = graphene.String(
        args={"key": graphene.NonNull(graphene.String)},
        description=(
            "A single key from private metadata. "
            "Requires staff permissions to access.\n\n"
            "Tip: Use GraphQL aliases to fetch multiple keys."
        ),
    )
    private_metafields = Metadata(
        args={"keys": NonNullList(graphene.String)},
        description=(
            "Private metadata. Requires staff permissions to access. "
            "Use `keys` to control which fields you want to include. "
            "The default is to include everything."
        ),
    )
    metadata = NonNullList(
        MetadataItem,
        required=True,
        description=(
            "List of public metadata items. Can be accessed without permissions."
        ),
    )
    metafield = graphene.String(
        args={"key": graphene.NonNull(graphene.String)},
        description=(
            "A single key from public metadata.\n\n"
            "Tip: Use GraphQL aliases to fetch multiple keys."
        ),
    )
    metafields = Metadata(
        args={"keys": NonNullList(graphene.String)},
        description=(
            "Public metadata. Use `keys` to control which fields you want to include. "
            "The default is to include everything."
        ),
    )

    @staticmethod
    def resolve_metadata(root: ModelWithMetadata, info: ResolveInfo):
        if isinstance(root, Checkout):
            from ..checkout.types import Checkout as CheckoutType

            return CheckoutType.resolve_metadata(root, info