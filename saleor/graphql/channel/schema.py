import graphene

from ...permission.auth_filters import AuthorizationFilters
from ..core import ResolveInfo
from ..core.descriptions import ADDED_IN_36, PREVIEW_FEATURE
from ..core.fields import PermissionsField
from ..core.types import NonNullList
from .mutations import (
    ChannelActivate,
    ChannelCreate,
    ChannelDeactivate,
    ChannelDelete,
    ChannelReorderWarehouses,
    Chan