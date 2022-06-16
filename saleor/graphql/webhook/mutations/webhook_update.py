import graphene

from ....permission.enums import AppPermission
from ....webhook import models
from ....webhook.validators import HEADERS_LENGTH_LIMIT, HEADERS_NUMBER_LIMIT
from ...core import ResolveInfo
from ...core.descriptions import (
    ADDED_IN_32,
    ADDED_IN_312,
    DEPRECATED_IN_3X_INPUT,
    PREVIEW_FEATURE,
)
from ...core.fields import JSONString
from ...core.types import NonNullList, WebhookError
from .. import enums
from ..types import Webhook
from . import WebhookCreate


class WebhookUpdateInput(graphene.InputObjectType):
    name = graphene.String(description="The new name of the webhook.", required=False)
    target_url = graphene.String(
        description="The url to receive the payload.", required=False
    )
    events = NonNullList(
        enums.WebhookEventTypeEnum,
        description=(
            f"The events that webhook wants to subscribe. {DEPRECATED_IN_3X_INPUT} "
            "Use `asyncEvents` or `syncEvents` instead."
        ),
        required=Fal