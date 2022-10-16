import logging
from collections import defaultdict
from typing import Dict, Iterable, List

from django.core.exceptions import ValidationError
from django.db.models import Value
from django.db.models.functions import Concat

from ..graphql.core.utils import str_to_enum
from ..graphql.webhook.subscription_query import SubscriptionQuery
from ..permission.enums import (
    get_permissions,
    get_permissions_enum_list,
    split_permission_codename,
)
from ..permission.models import Permission
from ..webhook.event_types import WebhookEventAsyncType, WebhookEventSyncType
from ..webhook.validators import custom_headers_validator
from .error_codes import AppErrorCode
from .types import AppExtensionMount, AppExtensionTarget
from .validators import AppURLValidator

logger = logging.getLogger(__name__)

T_ERRORS = Dict[str, List[ValidationError]]


def _clean_app_url(url):
    url_validator = AppURLValidator()
    url_validator(url)


def _clean_extension_url_with_only_path(
    manifest_data: dict, target: str, extension_url: str
):
    if target == AppExtensionTarget.APP_PAGE:
        return
    elif manifest_data["appUrl"]:
        _clean_app_url(manifest_data["appUrl"])
    else:
        msg = (
            "Incorrect relation between extension's target and URL fields. "
            "APP_PAGE can be used only with relative URL path."
        )
        logger.warning(msg, extra={"target": target, "url": extension_url})
        raise ValidationError(msg)


def clean_extension_url(extension: dict, manifest_data: dict):
    """Clean assigned extension url.

    Make sure that format of url is correct based on the rest of manifest fields.
    - url can start with 